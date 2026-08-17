"""
app.py
======
The web backend (API + static website server) for ResearchGuard AI.

It is a THIN layer around the existing, tested similarity engine:
  - pdf_processor.py  (extract + clean + chunk PDF text)
  - similarity.py     (embeddings + semantic/lexical/combined scoring)
  - main.py           (analyze_papers() pipeline + analysis.json)

The AI logic is NOT duplicated or changed - this file only:
  1. Serves the HTML/CSS/JS website (folder: website/)
  2. Receives PDF uploads through HTTP
  3. Calls main.analyze_papers() in a background thread
  4. Reports REAL progress while the analysis runs
  5. Stores each finished analysis in results/history/
  6. Answers the frontend's fetch() calls with JSON

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

import main as engine          # the existing prototype entry point
import similarity

# Set to True once the embedding model has finished loading into memory.
# The health endpoint reports "starting" until then, so the website can
# show "AI model loading..." instead of a scary error.
MODEL_READY = threading.Event()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEBSITE_FOLDER = os.path.join(BASE_DIR, "website")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
HISTORY_FOLDER = os.path.join(BASE_DIR, "results", "history")

MAX_FILE_SIZE_MB = 30

app = Flask(__name__, static_folder=None)  # we serve website/ manually below

# ---------------------------------------------------------------------------
# Shared state for the ONE analysis that can run at a time.
# (Simple and beginner-friendly. A queue would be overkill for a demo.)
# ---------------------------------------------------------------------------
analysis_state = {
    "job_id": None,
    "status": "idle",          # idle | uploading | running | done | error
    "step": None,              # machine step name from the engine
    "step_label": "",          # human-readable step text
    "percent": 0,              # real progress percent reported by the engine
    "error": None,
    "started_at": None,
    "finished_at": None,
    "result": None,            # the full results dictionary (analysis.json)
}

_state_lock = threading.Lock()  # keeps progress updates thread-safe


def set_state(**kwargs):
    """Safely update the shared analysis state from any thread."""
    with _state_lock:
        analysis_state.update(kwargs)


STEP_LABELS = {
    "uploading_papers": "Uploading papers",
    "extracting_reference_text": "Extracting reference paper text",
    "extracting_student_text": "Extracting student paper text",
    "creating_text_chunks": "Creating text chunks",
    "run_model": "Loading AI embedding model",
    "generating_embeddings": "Generating AI embeddings",
    "comparing_content": "Calculating similarity",
    "generating_report": "Generating report",
}


def run_analysis_job(reference_path, student_path, job_id, display_names):
    """
    Runs in a BACKGROUND THREAD so the web server stays responsive.

    Calls the ORIGINAL analyze_papers() from main.py - the same function
    the command-line prototype uses. No AI logic is duplicated here.
    """
    set_state(job_id=job_id, status="running", percent=2,
              step="uploading_papers", error=None, result=None,
              started_at=datetime.now().isoformat(timespec="seconds"),
              finished_at=None)

    def on_progress(step_name, percent):
        """Receives REAL progress from inside analyze_papers()."""
        label = STEP_LABELS.get(step_name, step_name.replace("_", " ").title())
        set_state(step=step_name, step_label=label, percent=int(percent))

    try:
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

        # Attach display info + a timestamp for the website & history
        results["reference_paper_name"] = display_names["reference"]
        results["student_paper_name"] = display_names["student"]
        results["timestamp"] = datetime.now().isoformat(timespec="seconds")
        results["job_id"] = job_id

        # Save into history so the History page has real stored data
        os.makedirs(HISTORY_FOLDER, exist_ok=True)
        history_path = os.path.join(HISTORY_FOLDER, f"{job_id}.json")
        with open(history_path, "w", encoding="utf-8") as f:
            import json
            json.dump(results, f, indent=2, ensure_ascii=False)

        set_state(status="done", percent=100, step="done",
                  step_label="Analysis complete", result=results,
                  finished_at=datetime.now().isoformat(timespec="seconds"))

    except Exception as error:  # show a friendly message, never a stack trace
        print(f"[backend] analysis failed: {error}")
        set_state(status="error", error=str(error))


# ---------------------------------------------------------------------------
# STATIC WEBSITE (HTML/CSS/JS in website/)
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    return send_from_directory(WEBSITE_FOLDER, "index.html")


@app.route("/<path:file_name>")
def serve_website_file(file_name):
    """Serve css/, js/, and the other .html pages."""
    return send_from_directory(WEBSITE_FOLDER, file_name)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.route("/api/health")
def api_health():
    """Frontend uses this to check the backend is alive."""
    if MODEL_READY.is_set():
        return jsonify({"status": "ok", "service": "ResearchGuard AI"})
    # Server is up but the AI model is still loading (first ~10-20 seconds)
    return jsonify({"status": "starting", "service": "ResearchGuard AI"})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    Receives the two uploaded PDFs and starts the real analysis.

    multipart/form-data fields expected:
        reference_pdf : the reference paper PDF file
        student_pdf   : the student paper PDF file
    """
    # --- validate uploads ---------------------------------------------------
    if analysis_state.get("status") == "running":
        return jsonify({"error": "An analysis is already running. Please wait for it to finish."}), 409

    if "reference_pdf" not in request.files or "student_pdf" not in request.files:
        return jsonify({"error": "Please upload both a reference and a student PDF."}), 400

    reference_file = request.files["reference_pdf"]
    student_file = request.files["student_pdf"]

    if reference_file.filename == "" or student_file.filename == "":
        return jsonify({"error": "Please upload both a reference and a student PDF."}), 400

    for uploaded in (reference_file, student_file):
        filename = uploaded.filename or ""
        if not filename.lower().endswith(".pdf"):
            return jsonify({"error": f"'{filename}' is not a PDF. Please upload valid PDF files."}), 400

    # --- save uploads to disk ------------------------------------------------
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    reference_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_reference.pdf")
    student_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_student.pdf")
    reference_file.save(reference_path)
    student_file.save(student_path)

    display_names = {
        "reference": os.path.basename(reference_file.filename),
        "student": os.path.basename(student_file.filename),
    }

    # --- start the REAL analysis in the background ---------------------------
    thread = threading.Thread(
        target=run_analysis_job,
        args=(reference_path, student_path, job_id, display_names),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "status": "started"}), 202


@app.route("/api/progress")
def api_progress():
    """Real-time progress polled by the processing screen."""
    with _state_lock:
        payload = dict(analysis_state)
    # The full result can be huge; only include it when finished
    if payload.get("status") != "done":
        payload.pop("result", None)
    return jsonify(payload)


@app.route("/api/results")
def api_results():
    """The latest completed analysis (for the results dashboard)."""
    with _state_lock:
        payload = dict(analysis_state)

    if payload.get("status") == "done" and payload.get("result"):
        return jsonify(payload["result"])

    # Fallback: newest file in results/history (survives server restarts)
    latest = _latest_history_file()
    if latest:
        return jsonify(_read_json(latest))

    return jsonify({"error": "No analysis results available yet. Please run an analysis first."}), 404


@app.route("/api/results/<job_id>")
def api_results_for_job(job_id):
    """One specific analysis by its job id (used by the History page)."""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", job_id)
    path = os.path.join(HISTORY_FOLDER, f"{safe_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Analysis not found."}), 404
    return jsonify(_read_json(path))


@app.route("/api/history")
def api_history():
    """Summary list of all stored analyses (newest first)."""
    items = []
    if os.path.isdir(HISTORY_FOLDER):
        files = sorted(os.listdir(HISTORY_FOLDER), reverse=True)
        for file_name in files:
            if not file_name.endswith(".json"):
                continue
            data = _read_json(os.path.join(HISTORY_FOLDER, file_name))
            if not data:
                continue
            items.append({
                "job_id": data.get("job_id", file_name[:-5]),
                "timestamp": data.get("timestamp", ""),
                "reference_paper_name": data.get("reference_paper_name", data.get("reference_paper", "")),
                "student_paper_name": data.get("student_paper_name", data.get("student_paper", "")),
                "overall_similarity": data.get("overall_similarity", 0),
                "high_similarity_matches": data.get("high_similarity_matches", 0),
                "medium_similarity_matches": data.get("medium_similarity_matches", 0),
                "low_similarity_matches": data.get("low_similarity_matches", 0),
            })
    return jsonify({"analyses": items})


@app.route("/api/history/<job_id>", methods=["DELETE"])
def api_delete_history_item(job_id):
    """Delete ONE stored analysis from the history."""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", job_id)
    path = os.path.join(HISTORY_FOLDER, f"{safe_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Analysis not found."}), 404
    try:
        os.remove(path)
        # Also remove the uploaded PDF copies for this job (if still present)
        for upload in os.listdir(UPLOAD_FOLDER) if os.path.isdir(UPLOAD_FOLDER) else []:
            if upload.startswith(safe_id + "_"):
                os.remove(os.path.join(UPLOAD_FOLDER, upload))
        return jsonify({"deleted": safe_id})
    except Exception as error:
        return jsonify({"error": f"Could not delete analysis: {error}"}), 500


@app.route("/api/history", methods=["DELETE"])
def api_clear_history():
    """Delete ALL stored analyses (the 'Clear All' button)."""
    deleted = 0
    if os.path.isdir(HISTORY_FOLDER):
        for file_name in os.listdir(HISTORY_FOLDER):
            if file_name.endswith(".json"):
                try:
                    os.remove(os.path.join(HISTORY_FOLDER, file_name))
                    deleted += 1
                except Exception:
                    pass  # skip files that cannot be deleted
    # Remove all uploaded PDF copies too
    if os.path.isdir(UPLOAD_FOLDER):
        for file_name in os.listdir(UPLOAD_FOLDER):
            if file_name.endswith(".pdf"):
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, file_name))
                except Exception:
                    pass
    return jsonify({"deleted_count": deleted})


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _read_json(path):
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as error:
        print(f"[backend] could not read {path}: {error}")
        return None


def _latest_history_file():
    if not os.path.isdir(HISTORY_FOLDER):
        return None
    files = [f for f in os.listdir(HISTORY_FOLDER) if f.endswith(".json")]
    if not files:
        return None
    files.sort(reverse=True)
    return os.path.join(HISTORY_FOLDER, files[0])


# ---------------------------------------------------------------------------
# START THE SERVER
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(HISTORY_FOLDER, exist_ok=True)
    print("=" * 50)
    print(" ResearchGuard AI - web backend starting...")
    print(" Website:  http://127.0.0.1:5000")
    print(" API health check: http://127.0.0.1:5000/api/health")
    print("=" * 50)
    # Start loading the embedding model in the BACKGROUND so the website
    # is reachable immediately (health returns "starting" meanwhile).
    def preload_model():
        print("Pre-loading embedding model (first run downloads it)...")
        similarity.load_embedding_model()
        MODEL_READY.set()
        print("Model ready. You can now run an analysis.")

    threading.Thread(target=preload_model, daemon=True).start()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
