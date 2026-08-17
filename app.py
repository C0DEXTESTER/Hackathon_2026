"""
app.py
======

ResearchGuard AI - Flask web backend.

This file is the web/API layer around the existing analysis engine:

    pdf_processor.py
        -> extracts and chunks PDF text

    similarity.py
        -> generates embeddings and calculates similarity

    main.py
        -> runs the complete analysis pipeline

    website/
        -> frontend HTML/CSS/JavaScript

Deployment:
    Local:
        python app.py

    Production:
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
# BASIC CONFIGURATION
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEBSITE_FOLDER = os.path.join(
    BASE_DIR,
    "website"
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

HISTORY_FOLDER = os.path.join(
    BASE_DIR,
    "results",
    "history"
)

# Maximum size for a single HTTP request.
MAX_FILE_SIZE_MB = 30


# ============================================================================
# FLASK APPLICATION
# ============================================================================

app = Flask(
    __name__,
    static_folder=None
)

# Enforce the 30 MB upload/request limit.
app.config["MAX_CONTENT_LENGTH"] = (
    MAX_FILE_SIZE_MB * 1024 * 1024
)


# ============================================================================
# MODEL READY STATE
# ============================================================================

# This event becomes set after FastEmbed has successfully loaded.
#
# IMPORTANT:
# We do NOT preload the model during Gunicorn startup.
# The model is loaded only when a real analysis is requested.
MODEL_READY = threading.Event()


# ============================================================================
# ANALYSIS STATE
# ============================================================================

# Only one analysis is allowed at a time.
#
# This keeps the application simple and prevents multiple large
# embedding operations from consuming memory simultaneously.

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
    """
    Safely update shared analysis state.

    A lock is used because the analysis runs in a background thread
    while Flask requests may read the same state simultaneously.
    """

    with _state_lock:
        analysis_state.update(kwargs)


# ============================================================================
# AI MODEL LOADING
# ============================================================================

def ensure_model_ready():
    """
    Load the AI embedding model only when required.

    This is intentionally lazy.

    Why?

    Render's free instance has limited RAM. Loading the model during
    Gunicorn startup would consume memory even when nobody is using
    the detector.

    The model is therefore loaded when the first analysis begins.
    """

    if MODEL_READY.is_set():
        return

    print(
        "[backend] Loading AI embedding model..."
    )

    similarity.load_embedding_model()

    MODEL_READY.set()

    print(
        "[backend] AI embedding model ready."
    )


# ============================================================================
# BACKGROUND ANALYSIS JOB
# ============================================================================

def run_analysis_job(
    reference_path,
    student_path,
    job_id,
    display_names,
):
    """
    Run the paper comparison in a background thread.

    This keeps Flask responsive while the AI analysis is running.
    """

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

    # ------------------------------------------------------------------------
    # Progress callback
    # ------------------------------------------------------------------------

    def on_progress(step_name, percent):
        """
        Receive progress updates from main.py.
        """

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

    # ------------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------------

    try:

        # Load the model only when an actual analysis is requested.
        ensure_model_ready()

        results = engine.analyze_papers(
            reference_pdf_path=reference_path,
            student_pdf_path=student_path,
            progress_callback=on_progress,
        )

        # --------------------------------------------------------------------
        # Validate result
        # --------------------------------------------------------------------

        if results is None:
            raise RuntimeError(
                "Not enough extractable text in the uploaded PDFs. "
                "Scanned/image-based PDFs are not supported yet."
            )

        # --------------------------------------------------------------------
        # Attach web application metadata
        # --------------------------------------------------------------------

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

        # --------------------------------------------------------------------
        # Save result to history
        # --------------------------------------------------------------------

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

        # --------------------------------------------------------------------
        # Mark analysis as complete
        # --------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------------

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
# STATIC WEBSITE
# ============================================================================

@app.route("/")
def serve_index():
    """
    Serve the main website page.
    """

    return send_from_directory(
        WEBSITE_FOLDER,
        "index.html"
    )


@app.route("/<path:file_name>")
def serve_website_file(file_name):
    """
    Serve frontend files such as:

        CSS
        JavaScript
        HTML
        images
    """

    return send_from_directory(
        WEBSITE_FOLDER,
        file_name
    )


# ============================================================================
# HEALTH API
# ============================================================================

@app.route("/api/health")
def api_health():
    """
    Health endpoint used by the frontend.

    IMPORTANT:
    This endpoint does NOT load the AI model.

    That keeps health checks fast and memory-efficient.
    """

    if MODEL_READY.is_set():

        return jsonify({
            "status": "ok",
            "service": "ResearchGuard AI",
        })

    return jsonify({
        "status": "starting",
        "service": "ResearchGuard AI",
    })


# ============================================================================
# ANALYZE API
# ============================================================================

@app.route(
    "/api/analyze",
    methods=["POST"]
)
def api_analyze():
    """
    Receive two PDF files:

        reference_pdf
        student_pdf

    Then start the analysis in a background thread.
    """

    # ------------------------------------------------------------------------
    # Check whether another analysis is already running
    # ------------------------------------------------------------------------

    with _state_lock:

        current_status = (
            analysis_state.get("status")
        )

    if current_status == "running":

        return jsonify({
            "error":
                "An analysis is already running. "
                "Please wait for it to finish."
        }), 409

    # ------------------------------------------------------------------------
    # Validate required files
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Validate filenames
    # ------------------------------------------------------------------------

    if (
        reference_file.filename == ""
        or
        student_file.filename == ""
    ):

        return jsonify({
            "error":
                "Please upload both a reference "
                "and a student PDF."
        }), 400

    # ------------------------------------------------------------------------
    # Validate PDF extensions
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Create upload directory
    # ------------------------------------------------------------------------

    os.makedirs(
        UPLOAD_FOLDER,
        exist_ok=True
    )

    # ------------------------------------------------------------------------
    # Generate unique job ID
    # ------------------------------------------------------------------------

    job_id = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        + "_"
        + uuid.uuid4().hex[:6]
    )

    # ------------------------------------------------------------------------
    # Create safe internal filenames
    # ------------------------------------------------------------------------

    reference_path = os.path.join(
        UPLOAD_FOLDER,
        f"{job_id}_reference.pdf"
    )

    student_path = os.path.join(
        UPLOAD_FOLDER,
        f"{job_id}_student.pdf"
    )

    # ------------------------------------------------------------------------
    # Save uploaded files
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Keep original display names
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Start background analysis
    # ------------------------------------------------------------------------

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
# PROGRESS API
# ============================================================================

@app.route("/api/progress")
def api_progress():
    """
    Return current analysis progress.
    """

    with _state_lock:

        payload = dict(
            analysis_state
        )

    # Do not send the full result while processing.
    if payload.get("status") != "done":

        payload.pop(
            "result",
            None
        )

    return jsonify(
        payload
    )


# ============================================================================
# RESULTS API
# ============================================================================

@app.route("/api/results")
def api_results():
    """
    Return the latest completed analysis.
    """

    with _state_lock:

        payload = dict(
            analysis_state
        )

    # ------------------------------------------------------------------------
    # Return current in-memory result
    # ------------------------------------------------------------------------

    if (
        payload.get("status") == "done"
        and
        payload.get("result")
    ):

        return jsonify(
            payload["result"]
        )

    # ------------------------------------------------------------------------
    # Fallback to saved history
    # ------------------------------------------------------------------------

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
# SPECIFIC RESULT API
# ============================================================================

@app.route(
    "/api/results/<job_id>"
)
def api_results_for_job(job_id):
    """
    Return one analysis by job ID.
    """

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
# HISTORY API
# ============================================================================

@app.route("/api/history")
def api_history():
    """
    Return a summary of stored analyses.
    """

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
    """
    Delete one stored analysis and its uploaded PDFs.
    """

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

        # Delete history JSON.
        os.remove(
            path
        )

        # Delete PDFs associated with the job.
        if os.path.isdir(
            UPLOAD_FOLDER
        ):

            for upload in os.listdir(
                UPLOAD_FOLDER
            ):

                if upload.startswith(
                    safe_id + "_"
                ):

                    upload_path = os.path.join(
                        UPLOAD_FOLDER,
                        upload
                    )

                    try:
                        os.remove(
                            upload_path
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
    """
    Delete all stored analyses and uploaded PDFs.
    """

    deleted = 0

    # ------------------------------------------------------------------------
    # Delete JSON history
    # ------------------------------------------------------------------------

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

            path = os.path.join(
                HISTORY_FOLDER,
                file_name
            )

            try:

                os.remove(
                    path
                )

                deleted += 1

            except OSError:

                pass

    # ------------------------------------------------------------------------
    # Delete uploaded PDFs
    # ------------------------------------------------------------------------

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

            path = os.path.join(
                UPLOAD_FOLDER,
                file_name
            )

            try:

                os.remove(
                    path
                )

            except OSError:

                pass

    return jsonify({
        "deleted_count": deleted
    })


# ============================================================================
# JSON HELPER
# ============================================================================

def _read_json(path):
    """
    Safely read a JSON file.
    """

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


# ============================================================================
# FIND LATEST HISTORY FILE
# ============================================================================

def _latest_history_file():
    """
    Find the newest stored analysis.
    """

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
# LOCAL DEVELOPMENT SERVER
# ============================================================================

if __name__ == "__main__":

    # Make sure required runtime directories exist.
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
    #
    # Do NOT preload the AI model here.
    #
    # It will be loaded by ensure_model_ready() when the first
    # analysis starts. This saves memory during startup.

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
    )
