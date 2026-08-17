"""
test_web_e2e.py — End-to-end test of the local website backend.

Starts app.py as a real server, uploads the sample PDFs through the
same /api/analyze endpoint the browser uses, waits for the real AI
analysis to finish, and verifies /api/progress, /api/results and
/api/history respond with correct data.

Run from the project folder:
    python tests/test_web_e2e.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

# Make imports/paths work no matter where the script is launched from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

BASE = "http://127.0.0.1:5000"
REFERENCE_PDF = os.path.join("papers", "reference.pdf")
STUDENT_PDF = os.path.join("papers", "student.pdf")


def http_get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        return response.status, json.loads(response.read().decode())


def wait_for_server(timeout=60):
    """Wait until /api/health responds (model loading can take a while)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            status, data = http_get("/api/health")
            if status == 200 and data.get("status") == "ok":
                return True
        except Exception:
            time.sleep(1)
    return False


def upload_pdfs():
    """Send both PDFs to /api/analyze exactly like the browser does."""
    boundary = "----ResearchGuardTestBoundary"

    def file_field(name, path):
        with open(path, "rb") as f:
            content = f.read()
        display_name = os.path.basename(path)  # what the server sees as filename
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{display_name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        return header + content + b"\r\n"

    body = (
        file_field("reference_pdf", REFERENCE_PDF)
        + file_field("student_pdf", STUDENT_PDF)
        + f"--{boundary}--\r\n".encode()
    )

    request = urllib.request.Request(
        BASE + "/api/analyze",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode())


def main():
    print("=" * 50)
    print(" WEB BACKEND END-TO-END TEST")
    print("=" * 50)

    if not (os.path.exists(REFERENCE_PDF) and os.path.exists(STUDENT_PDF)):
        print("Sample PDFs missing — creating them first...")
        subprocess.run(
            [sys.executable, os.path.join("tests", "make_sample_pdfs.py")],
            check=True,
        )

    # 1. Start the real server (same as `python app.py`)
    print("\n[1] Starting app.py ...")
    server = subprocess.Popen([sys.executable, "app.py"])
    try:
        print("[2] Waiting for /api/health ...")
        if not wait_for_server():
            raise RuntimeError("Server did not start within 60 seconds")
        print("    health OK")

        # 2. Upload both PDFs
        print("[3] POST /api/analyze (uploading PDFs) ...")
        status, data = upload_pdfs()
        # 202 Accepted = upload OK, analysis started in the background
        assert status in (200, 202) and "job_id" in data, f"Unexpected response: {data}"
        job_id = data["job_id"]
        print(f"    job started: {job_id}")

        # 3. Poll real progress until done
        print("[4] Polling /api/progress ...")
        deadline = time.time() + 600  # up to 10 minutes (first model download)
        while time.time() < deadline:
            _, progress = http_get("/api/progress")
            label = progress.get("step_label", "")
            percent = progress.get("percent", 0)
            print(f"    {percent:>3}%  {label}")

            if progress.get("status") == "done":
                break
            if progress.get("status") == "error":
                raise RuntimeError("Backend error: " + str(progress.get("error")))
            time.sleep(2)
        else:
            raise RuntimeError("Analysis did not finish in time")

        # 4. Verify the full results payload
        print("[5] GET /api/results ...")
        _, results = http_get("/api/results")
        for key in [
            "job_id",
            "overall_similarity",
            "semantic_similarity",
            "lexical_similarity",
            "combined_similarity",
            "high_similarity_matches",
            "medium_similarity_matches",
            "low_similarity_matches",
            "reference_chunk_count",
            "student_chunk_count",
            "top_matches",
        ]:
            assert key in results, f"Missing key in results: {key}"

        top = results["top_matches"][0]
        for key in [
            "student_chunk_id",
            "reference_chunk_id",
            "semantic_similarity",
            "lexical_similarity",
            "combined_similarity",
            "risk",
            "student_page",
            "reference_page",
            "student_text",
            "reference_text",
        ]:
            assert key in top, f"Missing key in top match: {key}"

        print(f"    overall similarity : {results['overall_similarity']:.3f}")
        print(f"    chunks             : {results['student_chunk_count']} student vs "
              f"{results['reference_chunk_count']} reference")
        print(f"    high/medium/low    : {results['high_similarity_matches']}/"
              f"{results['medium_similarity_matches']}/{results['low_similarity_matches']}")
        print(f"    top match combined : {top['combined_similarity']:.3f} "
              f"({top['risk']})")

        # 5. History endpoint
        print("[6] GET /api/history ...")
        _, history = http_get("/api/history")
        entries = history.get("analyses", [])
        assert any(a["job_id"] == job_id for a in entries), "Job not found in history"
        print(f"    history entries    : {len(entries)} (newest: {entries[0]['job_id']})")

        print("\nALL CHECKS PASSED (website backend works end-to-end)")

    finally:
        print("\n[7] Stopping server ...")
        server.terminate()
        server.wait(timeout=10)
        print("    stopped")


if __name__ == "__main__":
    main()