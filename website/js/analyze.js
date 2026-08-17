/*
   analyze.js — Upload cards + starting the real AI analysis.
   Flow: pick/drag PDFs -> POST /api/analyze -> poll /api/progress
   -> when done, go to results.html (which loads /api/results).

   Extras: animated SVG progress ring, elapsed timer, unload guard,
   toast notifications and auto backend re-check.
*/

// The two files the user selected
const selectedFiles = {
  reference: null,
  student: null,
};

const MAX_FILE_MB = 30;

const uploadSection = document.getElementById("uploadSection");
const processingSection = document.getElementById("processingSection");
const startButton = document.getElementById("startAnalysis");
const analyzeNote = document.getElementById("analyzeNote");

// SVG progress ring geometry: r=80 -> circumference ≈ 502.65
const RING_CIRCUMFERENCE = 2 * Math.PI * 80;

let analysisRunning = false;   // enables the "are you sure?" exit guard
let elapsedTimerId = null;
let analysisStartTime = 0;

// ---------------------------------------------------------------------------
// One uploader object per upload card (reference / student)
// ---------------------------------------------------------------------------
function setupUploader(role) {
  const input = document.getElementById(`${role}Input`);
  const dropZone = document.getElementById(`${role}Drop`);
  const card = document.getElementById(`${role}Card`);
  const info = document.getElementById(`${role}Info`);
  const errorEl = document.getElementById(`${role}Error`);

  const showError = (message) => {
    errorEl.textContent = message;
    errorEl.hidden = false;
    toast(message, "error");
  };
  const clearError = () => {
    errorEl.textContent = "";
    errorEl.hidden = true;
  };

  /** Validate + store the chosen file, then update the UI. */
  const handleFile = (file) => {
    clearError();

    const isPdf =
      file &&
      (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
    if (!isPdf) {
      showError("Please upload a valid PDF file.");
      return;
    }

    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      showError(`File size exceeds the allowed limit (${MAX_FILE_MB} MB).`);
      return;
    }

    selectedFiles[role] = file;

    dropZone.hidden = true;
    info.hidden = false;
    card.classList.add("has-file");
    document.getElementById(`${role}Name`).textContent = file.name;
    document.getElementById(`${role}Size`).textContent = formatFileSize(file.size);
    document.getElementById(`${role}Status`).textContent = "Ready for analysis";

    toast(`${file.name} uploaded`, "success", 2200);
    updateStartButton();
  };

  // --- click / keyboard opens the file picker -----------------------------
  dropZone.addEventListener("click", (event) => {
    if (event.target.tagName !== "INPUT") input.click();
  });
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });

  // --- file picker ---------------------------------------------------------
  input.addEventListener("change", () => {
    if (input.files && input.files[0]) handleFile(input.files[0]);
  });

  // --- drag & drop (highlight the whole card) ------------------------------
  ["dragenter", "dragover"].forEach((eventName) => {
    card.addEventListener(eventName, (event) => {
      event.preventDefault();
      card.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    card.addEventListener(eventName, (event) => {
      event.preventDefault();
      card.classList.remove("dragover");
    });
  });
  card.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // --- Change / Remove buttons ---------------------------------------------
  const changeBtn = document.getElementById(`${role}Change`);
  const removeBtn = document.getElementById(`${role}Remove`);
  if (changeBtn) changeBtn.addEventListener("click", () => input.click());
  if (removeBtn) {
    removeBtn.addEventListener("click", () => {
      selectedFiles[role] = null;
      input.value = "";
      info.hidden = true;
      dropZone.hidden = false;
      card.classList.remove("has-file");
      updateStartButton();
    });
  }
}

setupUploader("reference");
setupUploader("student");

// ---------------------------------------------------------------------------
// On page load: check the Python backend is actually running
// ---------------------------------------------------------------------------
async function checkBackendOnLoad() {
  if (location.protocol === "file:") {
    backendOnline = false;
    analyzeNote.textContent =
      "⚠ This page was opened directly from disk. Close it and use the server instead: " +
      "start start_website.bat, then open http://127.0.0.1:5000 in your browser.";
    analyzeNote.classList.add("backend-offline");
    return;
  }

  try {
    const health = await apiHealth();

    if (health.status === "starting") {
      backendOnline = false;
      analyzeNote.textContent = "⏳ AI model is loading… this page will update automatically.";
      analyzeNote.classList.remove("backend-offline");
      setTimeout(checkBackendOnLoad, 2000);
      return;
    }

    backendOnline = true;
    analyzeNote.classList.remove("backend-offline");
    updateStartButton();
  } catch (error) {
    backendOnline = false;
    analyzeNote.textContent =
      "⚠ Backend not running. Start it first with start_website.bat (or 'python app.py'), then refresh this page.";
    analyzeNote.classList.add("backend-offline");
    setTimeout(checkBackendOnLoad, 5000); // keep retrying quietly
  }
}

let backendOnline = false; // set true once the health check passes
checkBackendOnLoad();

// ---------------------------------------------------------------------------
// Enable the Start button only when BOTH files are selected
// ---------------------------------------------------------------------------
function updateStartButton() {
  const bothSelected = selectedFiles.reference && selectedFiles.student;
  startButton.disabled = !bothSelected || !backendOnline;
  if (!backendOnline) return;
  analyzeNote.textContent = bothSelected
    ? "Both PDFs are ready. Click Start AI Analysis."
    : "Upload both PDFs to enable analysis.";
}

// ---------------------------------------------------------------------------
// Warn the user if they try to leave while an analysis is running
// ---------------------------------------------------------------------------
window.addEventListener("beforeunload", (event) => {
  if (analysisRunning) {
    event.preventDefault();
    event.returnValue = "An analysis is still running — leaving will lose progress.";
    return event.returnValue;
  }
});

// ---------------------------------------------------------------------------
// Start the real analysis
// ---------------------------------------------------------------------------
startButton.addEventListener("click", async () => {
  clearProcessingUI();
  uploadSection.hidden = true;
  processingSection.hidden = false;
  processingSection.scrollIntoView({ behavior: "smooth" });

  analysisRunning = true;
  analysisStartTime = Date.now();
  startElapsedTimer();

  try {
    await apiStartAnalysis(selectedFiles.reference, selectedFiles.student);
    pollProgress();
  } catch (error) {
    showProcessingError(error.message);
  }
});

/** Reset the processing screen before a new run. */
function clearProcessingUI() {
  document.getElementById("processingError").hidden = true;
  document.getElementById("errorActions").hidden = true;
  document.getElementById("progressFill").style.width = "0%";
  document.getElementById("progressPercent").textContent = "0%";
  document.getElementById("processingStatus").textContent = "Uploading papers…";
  setRing(0);
  document.querySelectorAll("#stepList li").forEach((li) => {
    li.classList.remove("done", "active");
  });
}

/** Update the SVG ring + center percentage. */
function setRing(percent) {
  const offset = RING_CIRCUMFERENCE * (1 - Math.min(100, percent) / 100);
  const fill = document.getElementById("ringFill");
  if (fill) fill.style.strokeDashoffset = offset;
  document.getElementById("ringPercent").textContent = Math.round(percent) + "%";
  document.getElementById("progressRingBox").setAttribute("aria-valuenow", Math.round(percent));
}

/** Tick the "elapsed Xs" label once per second. */
function startElapsedTimer() {
  const etaEl = document.getElementById("ringEta");
  clearInterval(elapsedTimerId);
  elapsedTimerId = setInterval(() => {
    const seconds = Math.floor((Date.now() - analysisStartTime) / 1000);
    etaEl.textContent = `elapsed ${seconds}s`;
  }, 1000);
}
function stopElapsedTimer() {
  clearInterval(elapsedTimerId);
}

/** Ask the backend for REAL progress every second. */
function pollProgress() {
  const timer = setInterval(async () => {
    try {
      const progress = await apiGetProgress();
      updateProgressUI(progress);

      if (progress.status === "done") {
        clearInterval(timer);
        finishAnalysis();
      } else if (progress.status === "error") {
        clearInterval(timer);
        showProcessingError(progress.error || "Analysis failed. Please try again.");
      }
    } catch (error) {
      clearInterval(timer);
      showProcessingError("Lost connection to the backend. Is app.py still running?");
    }
  }, 1000);
}

/** Success path: stop timers, celebrate, then open the report. */
function finishAnalysis() {
  analysisRunning = false;
  stopElapsedTimer();

  const elapsed = Math.floor((Date.now() - analysisStartTime) / 1000);
  document.getElementById("ringEta").textContent = `done in ${elapsed}s`;
  setRing(100);
  toast("Analysis complete! Opening your report…", "success", 2500);

  setTimeout(() => {
    window.location.href = "results.html";
  }, 900);
}

/** Paint the real step + percent coming from Python onto the screen. */
function updateProgressUI(progress) {
  const percent = Math.max(0, Math.min(100, progress.percent || 0));
  document.getElementById("progressFill").style.width = percent + "%";
  document.getElementById("progressPercent").textContent = percent + "%";
  document.getElementById("processingStatus").textContent =
    progress.step_label || "Working…";
  setRing(percent);

  const stepOrder = [
    "uploading_papers",
    "extracting_reference_text",
    "extracting_student_text",
    "creating_text_chunks",
    "generating_embeddings",
    "comparing_content",
    "generating_report",
  ];

  const currentIndex = stepOrder.indexOf(progress.step);
  document.querySelectorAll("#stepList li").forEach((li) => {
    const index = stepOrder.indexOf(li.dataset.step);
    li.classList.toggle("done", currentIndex > index);
    li.classList.toggle("active", currentIndex === index && progress.status !== "done");
  });

  if (progress.status === "done") {
    document.querySelectorAll("#stepList li").forEach((li) => {
      li.classList.add("done");
      li.classList.remove("active");
    });
  }
}

function showProcessingError(message) {
  analysisRunning = false;
  stopElapsedTimer();
  const errorEl = document.getElementById("processingError");
  errorEl.textContent = "⚠️ " + message;
  errorEl.hidden = false;
  document.getElementById("errorActions").hidden = false;
  toast(message, "error", 4500);
}