"""
similarity.py
=============

AI logic for the Research Paper Similarity Detector.

Features:
    1. Load an open-source embedding model.
    2. Generate semantic embeddings using FastEmbed.
    3. Compare student-paper chunks with reference-paper chunks.
    4. Calculate semantic similarity.
    5. Calculate lexical similarity.
    6. Combine both scores.
    7. Classify similarity risk as LOW / MEDIUM / HIGH.

Deployment notes:
    - Uses FastEmbed instead of SentenceTransformers/PyTorch.
    - Uses ONNX Runtime for lightweight CPU inference.
    - Uses small embedding batches to reduce memory usage.
    - Avoids creating a huge complete similarity matrix.
"""

import os

# Keep ONNX Runtime resource usage conservative on small cloud instances.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import re
import threading
from difflib import SequenceMatcher

import numpy as np
from fastembed import TextEmbedding


# ---------------------------------------------------------------------------
# MODEL CACHE
# ---------------------------------------------------------------------------

# The model is loaded only once per Python process.
_loaded_model = None
_model_lock = threading.Lock()


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# FastEmbed's supported model identifier for the same MiniLM model
# previously used with SentenceTransformers.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Small batches help keep memory usage low on free cloud instances.
EMBEDDING_BATCH_SIZE = 4

# MiniLM produces 384-dimensional embeddings.
EMBEDDING_DIMENSION = 384


# ---------------------------------------------------------------------------
# SIMILARITY WEIGHTS
# ---------------------------------------------------------------------------

# Semantic similarity detects similar meaning/paraphrasing.
SEMANTIC_WEIGHT = 0.7

# Lexical similarity detects similar/identical wording.
LEXICAL_WEIGHT = 0.3


# ---------------------------------------------------------------------------
# RISK THRESHOLDS
# ---------------------------------------------------------------------------

LOW_THRESHOLD = 0.50
HIGH_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# STEP 1: LOAD EMBEDDING MODEL
# ---------------------------------------------------------------------------

def load_embedding_model(model_name=MODEL_NAME):
    """
    Load the FastEmbed model once and cache it.

    FastEmbed uses ONNX Runtime and is considerably lighter than loading
    the full SentenceTransformers/PyTorch stack.

    Returns:
        TextEmbedding:
            Loaded FastEmbed embedding model.
    """

    global _loaded_model

    with _model_lock:

        if _loaded_model is not None:
            return _loaded_model

        print(f"Loading embedding model '{model_name}' ...")

        _loaded_model = TextEmbedding(
            model_name=model_name,
            threads=1,
        )

        print("Embedding model ready.")

        return _loaded_model


# ---------------------------------------------------------------------------
# STEP 2: NORMALIZE EMBEDDINGS
# ---------------------------------------------------------------------------

def _normalize_embeddings(embeddings):
    """
    Normalize embedding vectors to unit length.

    Once vectors are normalized:

        cosine_similarity(A, B) = dot(A, B)

    This allows us to use NumPy dot products instead of sklearn.
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

    # Prevent division by zero.
    norms = np.maximum(norms, 1e-12)

    embeddings = embeddings / norms

    return embeddings.astype(np.float32)


# ---------------------------------------------------------------------------
# STEP 3: GENERATE EMBEDDINGS
# ---------------------------------------------------------------------------

def generate_embeddings(model, chunks):
    """
    Convert text chunks into normalized embedding vectors.

    Input:
        [
            {
                "chunk_id": 1,
                "text": "...",
                "page": 2
            },
            ...
        ]

    Output:
        NumPy array with shape:

            (number_of_chunks, 384)

    Memory optimization:
        FastEmbed returns embeddings through a generator.
        A small batch size keeps inference memory under control.
    """

    if not chunks:
        return np.empty(
            (0, EMBEDDING_DIMENSION),
            dtype=np.float32,
        )

    texts = [
        chunk["text"]
        for chunk in chunks
        if chunk.get("text")
    ]

    if not texts:
        return np.empty(
            (0, EMBEDDING_DIMENSION),
            dtype=np.float32,
        )

    print(
        f"Generating embeddings for {len(texts)} chunks "
        f"(batch size={EMBEDDING_BATCH_SIZE})..."
    )

    embedding_generator = model.embed(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
    )

    embeddings = np.asarray(
        list(embedding_generator),
        dtype=np.float32,
    )

    embeddings = _normalize_embeddings(embeddings)

    print(
        f"Generated embedding matrix: {embeddings.shape}"
    )

    return embeddings


# ---------------------------------------------------------------------------
# STEP 4: SEMANTIC SIMILARITY MATRIX
# ---------------------------------------------------------------------------

def calculate_semantic_similarity_matrix(
    reference_embeddings,
    student_embeddings,
):
    """
    Calculate semantic similarity between all student and reference
    embeddings.

    Because the vectors are normalized:

        cosine similarity = dot product

    Returns:

        Matrix with shape:

            (student_chunks, reference_chunks)

    NOTE:
        This function is kept for compatibility with the original
        project. The main matching function below avoids constructing
        the entire matrix when possible.
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
            (len(student_embeddings), len(reference_embeddings)),
            dtype=np.float32,
        )

    similarity_matrix = np.matmul(
        student_embeddings,
        reference_embeddings.T,
    )

    # Numerical safety.
    similarity_matrix = np.clip(
        similarity_matrix,
        -1.0,
        1.0,
    )

    return similarity_matrix.astype(np.float32)


# ---------------------------------------------------------------------------
# STEP 5: LEXICAL NORMALIZATION
# ---------------------------------------------------------------------------

def _normalize_for_lexical(text):
    """
    Normalize text before lexical comparison.

    Example:

        Machine-Learning algorithms are WIDELY used.

    becomes:

        machine learning algorithms are widely used
    """

    if not text:
        return ""

    text = text.lower()

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


# ---------------------------------------------------------------------------
# STEP 6: LEXICAL SIMILARITY
# ---------------------------------------------------------------------------

def calculate_lexical_similarity(text_1, text_2):
    """
    Calculate wording similarity using SequenceMatcher.

    Returns:
        Float from 0.0 to 1.0.
    """

    normalized_1 = _normalize_for_lexical(text_1)
    normalized_2 = _normalize_for_lexical(text_2)

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


# ---------------------------------------------------------------------------
# STEP 7: COMBINED SCORE
# ---------------------------------------------------------------------------

def calculate_combined_score(
    semantic_similarity,
    lexical_similarity,
):
    """
    Combine semantic and lexical similarity.

        combined =
            0.7 * semantic
            +
            0.3 * lexical
    """

    combined_score = (
        SEMANTIC_WEIGHT * semantic_similarity
        +
        LEXICAL_WEIGHT * lexical_similarity
    )

    return float(
        np.clip(
            combined_score,
            0.0,
            1.0,
        )
    )


# ---------------------------------------------------------------------------
# STEP 8: RISK CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_risk(combined_score):
    """
    Classify similarity risk.

        < 0.50        -> LOW
        0.50 - 0.75   -> MEDIUM
        >= 0.75       -> HIGH

    IMPORTANT:
        HIGH means high similarity.
        It does NOT automatically prove plagiarism.
    """

    if combined_score >= HIGH_THRESHOLD:
        return "HIGH"

    if combined_score >= LOW_THRESHOLD:
        return "MEDIUM"

    return "LOW"


# ---------------------------------------------------------------------------
# STEP 9: FIND BEST MATCHES
# ---------------------------------------------------------------------------

def find_best_matches(
    reference_chunks,
    student_chunks,
    reference_embeddings,
    student_embeddings,
):
    """
    Find the best reference match for every student chunk.

    Memory optimization:
        Instead of creating one huge:

            student_chunks x reference_chunks

        similarity matrix, this function processes one student
        embedding at a time.

    This is safer for cloud deployment with limited RAM.
    """

    if (
        not reference_chunks
        or not student_chunks
        or len(reference_embeddings) == 0
        or len(student_embeddings) == 0
    ):
        return []

    reference_embeddings = _normalize_embeddings(
        reference_embeddings
    )

    student_embeddings = _normalize_embeddings(
        student_embeddings
    )

    results = []

    # Make sure we never access more embeddings than chunks.
    student_count = min(
        len(student_chunks),
        len(student_embeddings),
    )

    reference_count = min(
        len(reference_chunks),
        len(reference_embeddings),
    )

    reference_embeddings = reference_embeddings[
        :reference_count
    ]

    reference_chunks = reference_chunks[
        :reference_count
    ]

    for row_index in range(student_count):

        student_chunk = student_chunks[row_index]

        student_vector = student_embeddings[
            row_index
        ]

        # Because both vectors are normalized:
        #
        # cosine similarity = dot product
        scores = np.dot(
            reference_embeddings,
            student_vector,
        )

        # Numerical safety.
        scores = np.clip(
            scores,
            -1.0,
            1.0,
        )

        best_reference_index = int(
            np.argmax(scores)
        )

        best_semantic = float(
            scores[best_reference_index]
        )

        best_reference_chunk = reference_chunks[
            best_reference_index
        ]

        # Lexical similarity is calculated only for the
        # best semantic match instead of every possible pair.
        best_lexical = calculate_lexical_similarity(
            student_chunk.get("text", ""),
            best_reference_chunk.get("text", ""),
        )

        combined = calculate_combined_score(
            best_semantic,
            best_lexical,
        )

        results.append(
            {
                "student_chunk_id": student_chunk["chunk_id"],

                "reference_chunk_id":
                    best_reference_chunk["chunk_id"],

                "semantic_similarity":
                    round(best_semantic, 4),

                "lexical_similarity":
                    round(best_lexical, 4),

                "combined_similarity":
                    round(combined, 4),

                "risk":
                    classify_risk(combined),

                "student_text":
                    student_chunk.get("text", ""),

                "reference_text":
                    best_reference_chunk.get("text", ""),

                "student_page":
                    student_chunk.get("page"),

                "reference_page":
                    best_reference_chunk.get("page"),
            }
        )

    return results


# ---------------------------------------------------------------------------
# STEP 10: OVERALL SIMILARITY
# ---------------------------------------------------------------------------

def calculate_overall_similarity(match_results):
    """
    Calculate the average best-match similarity.

    IMPORTANT:
        This is an experimental similarity score.

        It is NOT a confirmed plagiarism percentage.
    """

    if not match_results:
        return 0.0

    total = sum(
        match.get(
            "combined_similarity",
            0.0,
        )
        for match in match_results
    )

    average = total / len(
        match_results
    )

    return round(
        float(average),
        4,
    )
