"""
similarity.py
=============
This file contains all the "AI" logic of the prototype:

  1. Load a free, open-source embedding model (all-MiniLM-L6-v2)
  2. Turn text chunks into embeddings (numerical vectors)
  3. Compare student chunks with reference chunks:
       - semantic similarity  (cosine similarity of embeddings = MEANING)
       - lexical similarity   (SequenceMatcher = exact WORDING)
  4. Combine both scores into one number
  5. Classify the risk level (LOW / MEDIUM / HIGH)

---------------------------------------------------------------
WHAT IS AN EMBEDDING? (simple explanation)
---------------------------------------------------------------
An embedding is a list of numbers (a vector) that represents the
MEANING of a piece of text:

    Text: "AI is used in healthcare"
              |
              v
       Embedding Model
              |
              v
    [0.12, -0.45, 0.88, ..., 0.03]   <- 384 numbers for this model

Texts with similar meanings get vectors that point in similar
directions, even if the words are different:

    "AI is used in healthcare"      -> vector A
    "AI technologies are applied
     in the healthcare sector"      -> vector B  (close to A)

    "The football team won the
     championship yesterday"        -> vector C  (far from A)
---------------------------------------------------------------
"""

import re
import threading

import numpy as np
from difflib import SequenceMatcher
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

# Cache so the model is loaded into memory only ONCE, no matter how many
# times load_embedding_model() is called (CLI run, web server preload,
# or several analyses in a row).
_loaded_model = None
_model_lock = threading.Lock()


# ---------------------------------------------------------------------------
# CONFIGURATION - feel free to tune these numbers later
# ---------------------------------------------------------------------------

# The free/open-source embedding model from Hugging Face.
# all-MiniLM-L6-v2 is small (~80 MB), fast on CPU and works well for
# semantic similarity. First run downloads it automatically.
MODEL_NAME = "all-MiniLM-L6-v2"

# --- Combined score weights ------------------------------------------------
# How much each similarity type contributes to the final combined score.
# These are only INITIAL HEURISTIC (educated-guess) weights.
# They must eventually be calibrated with a proper labelled dataset.
SEMANTIC_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3

# --- Risk thresholds (on the combined score, scale 0.0 - 1.0) --------------
# Anything below HIGH_THRESHOLD is not considered suspicious on its own.
# These are preliminary values - tune them after testing with real papers.
LOW_THRESHOLD = 0.50    # below 0.50            -> LOW
HIGH_THRESHOLD = 0.75   # 0.50 to 0.75 -> MEDIUM, above 0.75 -> HIGH


# ---------------------------------------------------------------------------
# STEP 4: LOAD THE EMBEDDING MODEL
# ---------------------------------------------------------------------------

def load_embedding_model(model_name=MODEL_NAME):
    """
    Load the sentence-transformers model (only once - then cached).

    The first time this runs, the model (~80 MB) is downloaded from
    Hugging Face and cached on your computer. After that it loads
    from the cache and works completely offline.

    The lock makes this safe if two parts of the program (for example
    the web server's preload and a user's analysis) try to load the
    model at the same moment - the second one simply waits and reuses
    the already loaded model.
    """
    global _loaded_model
    with _model_lock:
        if _loaded_model is not None:
            return _loaded_model  # already in memory - reuse it

        print(f"  Loading embedding model '{model_name}' ...")
        _loaded_model = SentenceTransformer(model_name)
        print("  Model ready.")
        return _loaded_model


# ---------------------------------------------------------------------------
# STEP 5: GENERATE EMBEDDINGS
# ---------------------------------------------------------------------------

def generate_embeddings(model, chunks):
    """
    Convert a list of chunk dictionaries into embeddings.

    Input:  [{"chunk_id": 1, "text": "...", "page": 2}, ...]
    Output: a NumPy array, one row (vector) per chunk.

    model.encode() processes texts in batches internally, which is much
    faster than embedding them one by one.
    """
    # Pull the raw text out of every chunk dictionary
    texts = [chunk["text"] for chunk in chunks]

    # Convert all texts to vectors at once.
    # normalize_embeddings=True makes each vector length 1, which makes
    # cosine similarity a simple dot product (slightly faster & cleaner).
    embeddings = model.encode(
        texts,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    return np.array(embeddings)


# ---------------------------------------------------------------------------
# STEP 6: SEMANTIC SIMILARITY (MEANING)
# ---------------------------------------------------------------------------

def calculate_semantic_similarity_matrix(reference_embeddings, student_embeddings):
    """
    Compare EVERY student chunk with EVERY reference chunk.

    Returns a matrix (2D table) of cosine similarities:

                 ref_1   ref_2   ref_3  ...
        stu_1  [ 0.31    0.47    0.22  ]
        stu_2  [ 0.55    0.89    0.12  ]
        ...

    cosine_similarity ranges from -1 to 1, but for this model the
    interesting range is 0 (unrelated) to 1 (same meaning).

    WHY COSINE SIMILARITY?
    Because embeddings are directions in space: texts with the same
    meaning point in the same direction. Cosine similarity measures the
    angle between two vectors:
        1.0  -> same direction  -> same meaning
        0.0  -> perpendicular   -> unrelated
    """
    similarity_matrix = sklearn_cosine_similarity(
        student_embeddings,      # rows    = student chunks
        reference_embeddings,    # columns = reference chunks
    )
    return similarity_matrix


# ---------------------------------------------------------------------------
# STEP 7: LEXICAL SIMILARITY (EXACT WORDING)
# ---------------------------------------------------------------------------

def _normalize_for_lexical(text):
    """
    Simple normalization so SequenceMatcher compares words, not formatting.

    Example:
      "Machine-Learning algorithms are  WIDELY used."
      -> "machine learning algorithms are widely used"
    """
    text = text.lower()                # lowercase
    text = re.sub(r"[^a-z0-9\s]", " ", text)  # keep only letters/digits/spaces
    text = re.sub(r"\s+", " ", text)   # collapse spaces
    return text.strip()


def calculate_lexical_similarity(text_1, text_2):
    """
    Measure how similar two texts are WORD FOR WORD.

    Uses Python's built-in difflib.SequenceMatcher (the same engine
    behind file diff tools). It finds the longest matching blocks.

    Returns a score between 0.0 and 1.0:
      1.0 -> texts are (almost) identical
      0.0 -> nothing in common

    This catches DIRECT COPYING even when the semantic model is fooled
    by short or generic sentences.
    """
    normalized_1 = _normalize_for_lexical(text_1)
    normalized_2 = _normalize_for_lexical(text_2)

    if not normalized_1 or not normalized_2:
        return 0.0

    matcher = SequenceMatcher(None, normalized_1, normalized_2)
    return matcher.ratio()


# ---------------------------------------------------------------------------
# STEP 8: COMBINED SCORE
# ---------------------------------------------------------------------------

def calculate_combined_score(semantic_similarity, lexical_similarity):
    """
    Blend the two scores into one number.

        combined = 0.7 * semantic + 0.3 * lexical

    Semantic gets more weight because it also detects paraphrases
    (same meaning, different words). Lexical adds evidence for
    direct copy-paste.

    NOTE: the weights are initial heuristic values, not scientifically
    calibrated. A labelled dataset is needed to tune them properly.
    """
    combined_score = (
        SEMANTIC_WEIGHT * semantic_similarity
        + LEXICAL_WEIGHT * lexical_similarity
    )
    return combined_score


# ---------------------------------------------------------------------------
# RISK CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_risk(combined_score):
    """
    Turn a combined score into a human-readable risk label.

        < 0.50        -> "LOW"
        0.50 - 0.75   -> "MEDIUM"
        > 0.75        -> "HIGH"

    IMPORTANT: "HIGH" means HIGH SIMILARITY, NOT confirmed plagiarism.
    A human must always review the flagged passages.
    """
    if combined_score >= HIGH_THRESHOLD:
        return "HIGH"
    elif combined_score >= LOW_THRESHOLD:
        return "MEDIUM"
    else:
        return "LOW"


# ---------------------------------------------------------------------------
# FIND THE BEST MATCH FOR EVERY STUDENT CHUNK
# ---------------------------------------------------------------------------

def find_best_matches(reference_chunks, student_chunks,
                      reference_embeddings, student_embeddings):
    """
    For every student chunk:
      1. Compare it against ALL reference chunks (semantic similarity).
      2. Keep the single best (highest) semantic match.
      3. Compute lexical similarity for that best pair.
      4. Compute the combined score and classify the risk.

    Returns a list of result dictionaries:

        {
            "student_chunk_id": 5,
            "reference_chunk_id": 3,
            "semantic_similarity": 0.89,
            "lexical_similarity": 0.72,
            "combined_similarity": 0.84,
            "risk": "HIGH",
            "student_text": "...",
            "reference_text": "...",
            "student_page": 4,
            "reference_page": 5,
        }
    """
    # Table of semantic scores: rows = student chunks, cols = reference chunks
    similarity_matrix = calculate_semantic_similarity_matrix(
        reference_embeddings, student_embeddings
    )

    results = []

    for row_index, student_chunk in enumerate(student_chunks):
        # All similarity scores of THIS student chunk vs every reference chunk
        scores_against_references = similarity_matrix[row_index]

        # Index of the best (highest scoring) reference chunk
        best_reference_index = int(np.argmax(scores_against_references))
        best_semantic = float(scores_against_references[best_reference_index])

        best_reference_chunk = reference_chunks[best_reference_index]

        # Lexical similarity for the same best pair
        best_lexical = calculate_lexical_similarity(
            student_chunk["text"], best_reference_chunk["text"]
        )

        combined = calculate_combined_score(best_semantic, best_lexical)

        results.append(
            {
                "student_chunk_id": student_chunk["chunk_id"],
                "reference_chunk_id": best_reference_chunk["chunk_id"],
                "semantic_similarity": round(best_semantic, 4),
                "lexical_similarity": round(best_lexical, 4),
                "combined_similarity": round(combined, 4),
                "risk": classify_risk(combined),
                "student_text": student_chunk["text"],
                "reference_text": best_reference_chunk["text"],
                "student_page": student_chunk["page"],
                "reference_page": best_reference_chunk["page"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# OVERALL SIMILARITY
# ---------------------------------------------------------------------------

def calculate_overall_similarity(match_results):
    """
    One simple number that summarizes the whole comparison:

        average of the best-match combined similarity scores
        across all student chunks

    This is an EXPERIMENTAL similarity score for the prototype.
    It is NOT a "plagiarism percentage" - similarity alone never
    proves plagiarism.
    """
    if not match_results:
        return 0.0

    total = sum(match["combined_similarity"] for match in match_results)
    average = total / len(match_results)
    return round(average, 4)