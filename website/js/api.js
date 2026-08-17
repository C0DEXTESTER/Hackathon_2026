/*
   api.js — All communication with the Python backend.
   The frontend NEVER computes similarity itself; it only asks the
   backend (app.py) which runs the real AI engine, and displays the JSON.
*/

const API_BASE = ""; // same origin — the Flask server also hosts this website

/** Check that the Python backend is reachable. */
async function apiHealth() {
  const response = await fetch(`${API_BASE}/api/health`);
  if (!response.ok) throw new Error("Backend not reachable");
  return response.json(); // {status: "ok"} or {status: "starting"}
}

/** Upload both PDFs and start the real AI analysis. Returns {job_id}. */
async function apiStartAnalysis(referenceFile, studentFile) {
  const formData = new FormData();
  formData.append("reference_pdf", referenceFile);
  formData.append("student_pdf", studentFile);

  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body: formData,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Analysis failed. Please try again.");
  }
  return data;
}

/** Poll real progress while the backend runs the analysis. */
async function apiGetProgress() {
  const response = await fetch(`${API_BASE}/api/progress`);
  if (!response.ok) throw new Error("Could not read progress");
  return response.json();
}

/** Get the latest analysis results (full JSON). */
async function apiGetResults() {
  const response = await fetch(`${API_BASE}/api/results`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "No results available");
  return data;
}

/** Get one specific analysis by job id (from the History page). */
async function apiGetResultsById(jobId) {
  const response = await fetch(`${API_BASE}/api/results/${encodeURIComponent(jobId)}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Analysis not found");
  return data;
}

/** Get the list of stored analyses for the History page. */
async function apiGetHistory() {
  const response = await fetch(`${API_BASE}/api/history`);
  if (!response.ok) throw new Error("Could not load history");
  return response.json();
}

/** Delete ONE stored analysis from the history. */
async function apiDeleteHistoryItem(jobId) {
  const response = await fetch(`${API_BASE}/api/history/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not delete analysis");
  return data;
}

/** Delete ALL stored analyses (Clear All button). */
async function apiClearHistory() {
  const response = await fetch(`${API_BASE}/api/history`, { method: "DELETE" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not clear history");
  return data;
}
