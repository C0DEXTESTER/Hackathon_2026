"""
app.py
======
ResearchGuard AI - Flask web backend.

Local:
    python app.py

Render:
    gunicorn app:app --workers 1
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

import main as engine
import similarity


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEBSITE_FOLDER = os.path.join(BASE_DIR, "website")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
HISTORY_FOLDER = os.path.join(BASE_DIR, "results", "history")

MAX_FILE_SIZE_MB = 30


# ============================================================================
# FLASK
# ============================================================================

app = Flask(__name__, static_folder=None)

app.config["MAX_CONTENT_LENGTH"] = (
    MAX_FILE_SIZE_MB * 1024 * 1024
)


# ============================================================================
# MODEL STATE
# ============================================================================

# True only after FastEmbed has successfully loaded.
MODEL_READY = threading.Event()

# Prevent two requests from trying to load the model simultaneously.
MODEL_LOCK = threading.Lock()


# ============================================================================
# ANALYSIS STATE
# ============================================================================

analysis_state = {
    "job_id": None,
    "status": "idle",
    "step": None,
    "step_label": "",
    "percent": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
}

_state_lock = threading.Lock()


# ============================================================================
# PROGRESS LABELS
# ============================================================================

STEP_LABELS = {
    "uploading_papers":
        "Uploading papers",

    "extracting_reference_text":
        "Extracting reference paper text",

    "extracting_student_text":
        "Extracting student paper text",

    "creating_text_chunks":
        "Creating text chunks",

    "run_model":
        "Loading AI embedding model",

    "generating_embeddings":
        "Generating AI embeddings",

    "comparing_content":
        "Calculating similarity",

    "generating_report":
        "Generating report",
}


# ============================================================================
# STATE HELPER
# ============================================================================

def set_state(**kwargs):
    """Thread-safe update of analysis state."""

    with _state_lock:
        analysis_state.update(kwargs)


# ============================================================================
# AI MODEL
# ============================================================================

def ensure_model_ready():
    """
    Load the FastEmbed model when the first analysis starts.

    The model is NOT loaded during Render/Gunicorn startup.
    """

    if MODEL_READY.is_set():
        return

    with MODEL_LOCK:

        # Another thread may have loaded it while we waited.
        if MODEL_READY.is_set():
            return

        print("[backend] Loading AI embedding model...")

        similarity.load_embedding_model()

        MODEL_READY.set()

        print("[backend] AI embedding model ready.")


# ============================================================================
# BACKGROUND ANALYSIS
# ============================================================================

def run_analysis_job(
    reference_path,
    student_path,
    job_id,
    display_names,
):

    set_state(
        job_id=job_id,
        status="running",
        percent=2,
        step="uploading_papers",
        step_label="Uploading papers",
        error=None,
        result=None,
        started_at=datetime.now().isoformat(
            timespec="seconds"
        ),
        finished_at=None,
    )

    def on_progress(step_name, percent):

        label = STEP_LABELS.get(
            step_name,
            step_name.replace(
                "_",
                " "
            ).title()
        )

        set_state(
            step=step_name,
            step_label=label,
            percent=int(percent),
        )

    try:

        # ------------------------------------------------------------
        # Load AI model
        # ------------------------------------------------------------

        set_state(
            step="run_model",
            step_label="Loading AI embedding model",
            percent=5,
        )

        ensure_model_ready()

        # ------------------------------------------------------------
        # Run existing AI pipeline
        # ------------------------------------------------------------

        results = engine.analyze_papers(
            reference_pdf_path=reference_path,
            student_pdf_path=student_path,
            progress_callback=on_progress,
        )

        if results is None:

            raise RuntimeError(
                "Not enough extractable text in the uploaded PDFs. "
                "Scanned/image-based PDFs are not supported yet."
            )

        # ------------------------------------------------------------
        # Add website metadata
        # ------------------------------------------------------------

        results["reference_paper_name"] = (
            display_names["reference"]
        )

        results["student_paper_name"] = (
            display_names["student"]
        )

        results["timestamp"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        results["job_id"] = job_id

        # ------------------------------------------------------------
        # Save history
        # ------------------------------------------------------------

        os.makedirs(
            HISTORY_FOLDER,
            exist_ok=True
        )

        history_path = os.path.join(
            HISTORY_FOLDER,
            f"{job_id}.json"
        )

        with open(
            history_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                results,
                file,
                indent=2,
                ensure_ascii=False,
            )

        # ------------------------------------------------------------
        # Finished
        # ------------------------------------------------------------

        set_state(
            status="done",
            percent=100,
            step="done",
            step_label="Analysis complete",
            result=results,
            finished_at=datetime.now().isoformat(
                timespec="seconds"
            ),
        )

        print(
            f"[backend] Analysis {job_id} completed."
        )

    except Exception as error:

        print(
            f"[backend] Analysis {job_id} failed: {error}"
        )

        set_state(
            status="error",
            error=str(error),
            finished_at=datetime.now().isoformat(
                timespec="seconds"
            ),
        )


# ============================================================================
# WEBSITE
# ============================================================================

@app.route("/")
def serve_index():

    return send_from_directory(
        WEBSITE_FOLDER,
        "index.html"
    )


@app.route("/<path:file_name>")
def serve_website_file(file_name):

    return send_from_directory(
        WEBSITE_FOLDER,
        file_name
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route("/api/health")
def api_health():
    """
    IMPORTANT:

    Backend is considered healthy even when the AI model
    has not been loaded yet.

    The frontend can use model_ready to know whether the
    model is loaded.
    """

    return jsonify({
        "status": "ok",
        "service": "ResearchGuard AI",
        "model_ready": MODEL_READY.is_set(),
    })


# ============================================================================
# ANALYZE
# ============================================================================

@app.route(
    "/api/analyze",
    methods=["POST"]
)
def api_analyze():

    # ------------------------------------------------------------
    # Check current analysis
    # ------------------------------------------------------------

    with _state_lock:

        current_status = analysis_state.get(
            "status"
        )

    if current_status == "running":

        return jsonify({
            "error":
                "An analysis is already running. "
                "Please wait for it to finish."
        }), 409

    # ------------------------------------------------------------
    # Check uploaded files
    # ------------------------------------------------------------

    if (
        "reference_pdf" not in request.files
        or
        "student_pdf" not in request.files
    ):

        return jsonify({
            "error":
                "Please upload both a reference "
                "and a student PDF."
        }), 400

    reference_file = request.files[
        "reference_pdf"
    ]

    student_file = request.files[
        "student_pdf"
    ]

    # ------------------------------------------------------------
    # Check filenames
    # ------------------------------------------------------------

    if (
        not reference_file.filename
        or
        not student_file.filename
    ):

        return jsonify({
            "error":
                "Please upload both a reference "
                "and a student PDF."
        }), 400

    # ------------------------------------------------------------
    # Check PDF extensions
    # ------------------------------------------------------------

    for uploaded_file in (
        reference_file,
        student_file,
    ):

        filename = (
            uploaded_file.filename
            or ""
        )

        if not filename.lower().endswith(".pdf"):

            return jsonify({
                "error":
                    f"'{filename}' is not a PDF. "
                    "Please upload valid PDF files."
            }), 400

    # ------------------------------------------------------------
    # Create upload directory
    # ------------------------------------------------------------

    os.makedirs(
        UPLOAD_FOLDER,
        exist_ok=True
    )

    # ------------------------------------------------------------
    # Generate job ID
    # ------------------------------------------------------------

    job_id = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        + "_"
        + uuid.uuid4().hex[:6]
    )

    # ------------------------------------------------------------
    # Internal filenames
    # ------------------------------------------------------------

    reference_path = os.path.join(
        UPLOAD_FOLDER,
        f"{job_id}_reference.pdf"
    )

    student_path = os.path.join(
        UPLOAD_FOLDER,
        f"{job_id}_student.pdf"
    )

    # ------------------------------------------------------------
    # Save PDFs
    # ------------------------------------------------------------

    try:

        reference_file.save(
            reference_path
        )

        student_file.save(
            student_path
        )

    except Exception as error:

        return jsonify({
            "error":
                f"Could not save uploaded files: {error}"
        }), 500

    # ------------------------------------------------------------
    # Display names
    # ------------------------------------------------------------

    display_names = {

        "reference":
            os.path.basename(
                reference_file.filename
            ),

        "student":
            os.path.basename(
                student_file.filename
            ),
    }

    # ------------------------------------------------------------
    # Start background job
    # ------------------------------------------------------------

    thread = threading.Thread(
        target=run_analysis_job,
        args=(
            reference_path,
            student_path,
            job_id,
            display_names,
        ),
        daemon=True,
    )

    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "started",
    }), 202


# ============================================================================
# PROGRESS
# ============================================================================

@app.route("/api/progress")
def api_progress():

    with _state_lock:

        payload = dict(
            analysis_state
        )

    # Don't send huge result while processing.
    if payload.get("status") != "done":

        payload.pop(
            "result",
            None
        )

    return jsonify(
        payload
    )


# ============================================================================
# RESULTS
# ============================================================================

@app.route("/api/results")
def api_results():

    with _state_lock:

        payload = dict(
            analysis_state
        )

    # Current result
    if (
        payload.get("status") == "done"
        and
        payload.get("result")
    ):

        return jsonify(
            payload["result"]
        )

    # Saved history fallback
    latest = _latest_history_file()

    if latest:

        result = _read_json(
            latest
        )

        if result:

            return jsonify(
                result
            )

    return jsonify({
        "error":
            "No analysis results available yet. "
            "Please run an analysis first."
    }), 404


# ============================================================================
# SPECIFIC RESULT
# ============================================================================

@app.route(
    "/api/results/<job_id>"
)
def api_results_for_job(job_id):

    safe_id = re.sub(
        r"[^A-Za-z0-9_-]",
        "",
        job_id
    )

    path = os.path.join(
        HISTORY_FOLDER,
        f"{safe_id}.json"
    )

    if not os.path.exists(path):

        return jsonify({
            "error":
                "Analysis not found."
        }), 404

    result = _read_json(
        path
    )

    if result is None:

        return jsonify({
            "error":
                "Could not read analysis."
        }), 500

    return jsonify(
        result
    )


# ============================================================================
# HISTORY
# ============================================================================

@app.route("/api/history")
def api_history():

    items = []

    if os.path.isdir(
        HISTORY_FOLDER
    ):

        files = sorted(
            os.listdir(
                HISTORY_FOLDER
            ),
            reverse=True,
        )

        for file_name in files:

            if not file_name.endswith(
                ".json"
            ):
                continue

            path = os.path.join(
                HISTORY_FOLDER,
                file_name
            )

            data = _read_json(
                path
            )

            if not data:
                continue

            items.append({

                "job_id":
                    data.get(
                        "job_id",
                        file_name[:-5],
                    ),

                "timestamp":
                    data.get(
                        "timestamp",
                        "",
                    ),

                "reference_paper_name":
                    data.get(
                        "reference_paper_name",
                        data.get(
                            "reference_paper",
                            "",
                        ),
                    ),

                "student_paper_name":
                    data.get(
                        "student_paper_name",
                        data.get(
                            "student_paper",
                            "",
                        ),
                    ),

                "overall_similarity":
                    data.get(
                        "overall_similarity",
                        0,
                    ),

                "high_similarity_matches":
                    data.get(
                        "high_similarity_matches",
                        0,
                    ),

                "medium_similarity_matches":
                    data.get(
                        "medium_similarity_matches",
                        0,
                    ),

                "low_similarity_matches":
                    data.get(
                        "low_similarity_matches",
                        0,
                    ),
            })

    return jsonify({
        "analyses": items
    })


# ============================================================================
# DELETE ONE HISTORY ITEM
# ============================================================================

@app.route(
    "/api/history/<job_id>",
    methods=["DELETE"]
)
def api_delete_history_item(job_id):

    safe_id = re.sub(
        r"[^A-Za-z0-9_-]",
        "",
        job_id
    )

    path = os.path.join(
        HISTORY_FOLDER,
        f"{safe_id}.json"
    )

    if not os.path.exists(path):

        return jsonify({
            "error":
                "Analysis not found."
        }), 404

    try:

        os.remove(
            path
        )

        if os.path.isdir(
            UPLOAD_FOLDER
        ):

            for upload in os.listdir(
                UPLOAD_FOLDER
            ):

                if upload.startswith(
                    safe_id + "_"
                ):

                    try:

                        os.remove(
                            os.path.join(
                                UPLOAD_FOLDER,
                                upload
                            )
                        )

                    except OSError:
                        pass

        return jsonify({
            "deleted": safe_id
        })

    except Exception as error:

        return jsonify({
            "error":
                f"Could not delete analysis: {error}"
        }), 500


# ============================================================================
# DELETE ALL HISTORY
# ============================================================================

@app.route(
    "/api/history",
    methods=["DELETE"]
)
def api_clear_history():

    deleted = 0

    # Delete history
    if os.path.isdir(
        HISTORY_FOLDER
    ):

        for file_name in os.listdir(
            HISTORY_FOLDER
        ):

            if not file_name.endswith(
                ".json"
            ):
                continue

            try:

                os.remove(
                    os.path.join(
                        HISTORY_FOLDER,
                        file_name
                    )
                )

                deleted += 1

            except OSError:
                pass

    # Delete uploaded PDFs
    if os.path.isdir(
        UPLOAD_FOLDER
    ):

        for file_name in os.listdir(
            UPLOAD_FOLDER
        ):

            if not file_name.lower().endswith(
                ".pdf"
            ):
                continue

            try:

                os.remove(
                    os.path.join(
                        UPLOAD_FOLDER,
                        file_name
                    )
                )

            except OSError:
                pass

    return jsonify({
        "deleted_count": deleted
    })


# ============================================================================
# HELPERS
# ============================================================================

def _read_json(path):

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    except Exception as error:

        print(
            f"[backend] Could not read {path}: {error}"
        )

        return None


def _latest_history_file():

    if not os.path.isdir(
        HISTORY_FOLDER
    ):
        return None

    files = [
        file_name
        for file_name in os.listdir(
            HISTORY_FOLDER
        )
        if file_name.endswith(
            ".json"
        )
    ]

    if not files:
        return None

    files.sort(
        reverse=True
    )

    return os.path.join(
        HISTORY_FOLDER,
        files[0]
    )


# ============================================================================
# LOCAL SERVER
# ============================================================================

if __name__ == "__main__":

    os.makedirs(
        UPLOAD_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        HISTORY_FOLDER,
        exist_ok=True
    )

    print("=" * 55)
    print(" ResearchGuard AI - Web Backend")
    print("=" * 55)
    print(
        " Website: http://127.0.0.1:5000"
    )
    print(
        " Health:  http://127.0.0.1:5000/api/health"
    )
    print("=" * 55)

    # IMPORTANT:
    # Model is NOT loaded here.
    # It loads when the user starts an analysis.

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
    )
