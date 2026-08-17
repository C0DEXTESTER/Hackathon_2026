"""
similarity.py
=============

AI logic for the Research Paper Similarity Detector.

Uses FastEmbed + ONNX Runtime instead of SentenceTransformers/PyTorch.

Features:
    - Semantic similarity using embeddings
    - Lexical similarity using SequenceMatcher
    - Combined similarity score
    - LOW / MEDIUM / HIGH classification
    - Memory-conscious processing for small cloud instances
"""

import os

# Keep ONNX Runtime conservative on Render Free / small instances.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import re
import threading
from difflib import SequenceMatcher

import numpy as np
from fastembed import TextEmbedding


# ============================================================
# MODEL CACHE
# ============================================================

_loaded_model = None
_model_lock = threading.Lock()


# ============================================================
# CONFIGURATION
# ============================================================

# Officially supported by FastEmbed.
# Produces 384-dimensional embeddings.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Small batches reduce memory usage.
EMBEDDING_BATCH_SIZE = 4

EMBEDDING_DIMENSION = 384


# ============================================================
# SIMILARITY WEIGHTS
# ============================================================

SEMANTIC_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3


# ============================================================
# RISK THRESHOLDS
# ============================================================

LOW_THRESHOLD = 0.50
HIGH_THRESHOLD = 0.75


# ============================================================
# LOAD EMBEDDING MODEL
# ============================================================

def load_embedding_model(model_name=MODEL_NAME):
    """
    Load the FastEmbed model only once.

    The first call downloads the model.
    Later calls reuse the same model instance.
    """

    global _loaded_model

    with _model_lock:

        if _loaded_model is not None:
            return _loaded_model

        print("=" * 60)
        print(f"Loading AI embedding model: {model_name}")
        print("Using FastEmbed / ONNX Runtime")
        print("=" * 60)

        try:
            _loaded_model = TextEmbedding(
                model_name=model_name,
                threads=1,
            )

            print("AI embedding model loaded successfully.")
            print("=" * 60)

            return _loaded_model

        except Exception as error:
            print("=" * 60)
            print("ERROR: Could not load embedding model.")
            print(str(error))
            print("=" * 60)

            raise


# ============================================================
# NORMALIZE EMBEDDINGS
# ============================================================

def _normalize_embeddings(embeddings):
    """
    Normalize embedding vectors to unit length.

    After normalization:

        cosine_similarity(A, B) = dot(A, B)
    """

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    if embeddings.size == 0:
        return embeddings

    if embeddings.ndim == 1:
        embeddings = embeddings.reshape(1, -1)

    norms = np.linalg.norm(
        embeddings,
        axis=1,
        keepdims=True,
    )

    norms = np.maximum(
        norms,
        1e-12,
    )

    embeddings = embeddings / norms

    return embeddings.astype(np.float32)


# ============================================================
# GENERATE EMBEDDINGS
# ============================================================

def generate_embeddings(model, chunks):
    """
    Generate one embedding for every chunk.

    The order of the returned embeddings always matches
    the order of the supplied chunks.
    """

    if not chunks:
        return np.empty(
            (0, EMBEDDING_DIMENSION),
            dtype=np.float32,
        )

    # Keep one text for every chunk.
    # Do NOT remove empty chunks because doing so would
    # break the index relationship between chunks and embeddings.
    texts = [
        str(chunk.get("text", "") or "")
        for chunk in chunks
    ]

    print(
        f"Generating embeddings for {len(texts)} chunks..."
    )

    try:

        embedding_generator = model.embed(
            texts,
            batch_size=EMBEDDING_BATCH_SIZE,
        )

        embeddings = np.asarray(
            list(embedding_generator),
            dtype=np.float32,
        )

        embeddings = _normalize_embeddings(
            embeddings
        )

        print(
            f"Embedding matrix created: {embeddings.shape}"
        )

        return embeddings

    except Exception as error:

        print(
            f"Embedding generation failed: {error}"
        )

        raise


# ============================================================
# SEMANTIC SIMILARITY MATRIX
# ============================================================

def calculate_semantic_similarity_matrix(
    reference_embeddings,
    student_embeddings,
):
    """
    Calculate cosine similarity between every student
    chunk and every reference chunk.

    Shape:

        students x references
    """

    reference_embeddings = _normalize_embeddings(
        reference_embeddings
    )

    student_embeddings = _normalize_embeddings(
        student_embeddings
    )

    if (
        len(reference_embeddings) == 0
        or len(student_embeddings) == 0
    ):
        return np.empty(
            (
                len(student_embeddings),
                len(reference_embeddings),
            ),
            dtype=np.float32,
        )

    similarity_matrix = np.matmul(
        student_embeddings,
        reference_embeddings.T,
    )

    similarity_matrix = np.clip(
        similarity_matrix,
        -1.0,
        1.0,
    )

    return similarity_matrix.astype(
        np.float32
    )


# ============================================================
# LEXICAL NORMALIZATION
# ============================================================

def _normalize_for_lexical(text):
    """
    Normalize text before word-level comparison.
    """

    if not text:
        return ""

    text = str(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# LEXICAL SIMILARITY
# ============================================================

def calculate_lexical_similarity(
    text_1,
    text_2,
):
    """
    Calculate similarity based on exact wording.

    Returns:
        0.0 - 1.0
    """

    normalized_1 = _normalize_for_lexical(
        text_1
    )

    normalized_2 = _normalize_for_lexical(
        text_2
    )

    if not normalized_1 or not normalized_2:
        return 0.0

    matcher = SequenceMatcher(
        None,
        normalized_1,
        normalized_2,
    )

    return float(
        matcher.ratio()
    )


# ============================================================
# COMBINED SCORE
# ============================================================

def calculate_combined_score(
    semantic_similarity,
    lexical_similarity,
):
    """
    Combine semantic and lexical similarity.

        70% semantic
        30% lexical
    """

    combined_score = (
        SEMANTIC_WEIGHT
        * semantic_similarity
        +
        LEXICAL_WEIGHT
        * lexical_similarity
    )

    return float(
        np.clip(
            combined_score,
            0.0,
            1.0,
        )
    )


# ============================================================
# RISK CLASSIFICATION
# ============================================================

def classify_risk(combined_score):
    """
    Classify similarity level.

        < 0.50       LOW
        0.50-0.749   MEDIUM
        >= 0.75      HIGH

    HIGH means high similarity.
    It does NOT automatically prove plagiarism.
    """

    if combined_score >= HIGH_THRESHOLD:
        return "HIGH"

    if combined_score >= LOW_THRESHOLD:
        return "MEDIUM"

    return "LOW"


# ============================================================
# FIND BEST MATCHES
# ============================================================

def find_best_matches(
    reference_chunks,
    student_chunks,
    reference_embeddings,
    student_embeddings,
):
    """
    Find the best reference match for every student chunk.

    Processes one student embedding at a time instead of
    keeping a complete similarity matrix in memory.
    """

    if not reference_chunks:
        return []

    if not student_chunks:
        return []

    if len(reference_embeddings) == 0:
        return []

    if len(student_embeddings) == 0:
        return []

    reference_embeddings = _normalize_embeddings(
        reference_embeddings
    )

    student_embeddings = _normalize_embeddings(
        student_embeddings
    )

    # Prevent index errors if something unexpected happens.
    reference_count = min(
        len(reference_chunks),
        len(reference_embeddings),
    )

    student_count = min(
        len(student_chunks),
        len(student_embeddings),
    )

    reference_chunks = reference_chunks[
        :reference_count
    ]

    reference_embeddings = reference_embeddings[
        :reference_count
    ]

    results = []

    for row_index in range(student_count):

        student_chunk = student_chunks[
            row_index
        ]

        student_vector = student_embeddings[
            row_index
        ]

        # Cosine similarity because vectors are normalized.
        scores = np.dot(
            reference_embeddings,
            student_vector,
        )

        scores = np.clip(
            scores,
            -1.0,
            1.0,
        )

        best_reference_index = int(
            np.argmax(scores)
        )

        best_semantic = float(
            scores[
                best_reference_index
            ]
        )

        best_reference_chunk = (
            reference_chunks[
                best_reference_index
            ]
        )

        # Only calculate lexical similarity
        # for the best semantic match.
        best_lexical = (
            calculate_lexical_similarity(
                student_chunk.get(
                    "text",
                    "",
                ),
                best_reference_chunk.get(
                    "text",
                    "",
                ),
            )
        )

        combined = calculate_combined_score(
            best_semantic,
            best_lexical,
        )

        results.append(
            {
                "student_chunk_id":
                    student_chunk.get(
                        "chunk_id"
                    ),

                "reference_chunk_id":
                    best_reference_chunk.get(
                        "chunk_id"
                    ),

                "semantic_similarity":
                    round(
                        best_semantic,
                        4,
                    ),

                "lexical_similarity":
                    round(
                        best_lexical,
                        4,
                    ),

                "combined_similarity":
                    round(
                        combined,
                        4,
                    ),

                "risk":
                    classify_risk(
                        combined
                    ),

                "student_text":
                    student_chunk.get(
                        "text",
                        "",
                    ),

                "reference_text":
                    best_reference_chunk.get(
                        "text",
                        "",
                    ),

                "student_page":
                    student_chunk.get(
                        "page"
                    ),

                "reference_page":
                    best_reference_chunk.get(
                        "page"
                    ),
            }
        )

    return results


# ============================================================
# OVERALL SIMILARITY
# ============================================================

def calculate_overall_similarity(
    match_results,
):
    """
    Calculate the average best-match similarity.

    This is an experimental similarity score.

    It is NOT a confirmed plagiarism percentage.
    """

    if not match_results:
        return 0.0

    total = sum(
        float(
            match.get(
                "combined_similarity",
                0.0,
            )
        )
        for match in match_results
    )

    average = (
        total
        / len(match_results)
    )

    return round(
        float(average),
        4,
    )
