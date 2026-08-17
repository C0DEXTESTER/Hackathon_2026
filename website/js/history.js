/*
   history.js — Browse, search, sort, open or delete past analyses.
   Uses the real backend endpoints (/api/history, DELETE /api/history/:id).
   Includes quick stats cards and a custom confirm dialog (no window.confirm).
*/

let allHistory = [];
let searchQuery = "";
let sortMode = "date-desc";

document.addEventListener("DOMContentLoaded", loadHistory);

async function loadHistory() {
  const loading = document.getElementById("historyLoading");
  const content = document.getElementById("historyContent");
  const empty = document.getElementById("historyEmpty");

  try {
    const data = await apiGetHistory();
    allHistory = data.analyses || [];
    loading.hidden = true;
    content.hidden = false;
    renderStats();
    renderList();
  } catch (error) {
    loading.hidden = true;
    content.hidden = true;
    empty.hidden = false;
  }
}

// ---------------------------------------------------------------------------
// Quick stats strip (total, average, highest, flagged)
// ---------------------------------------------------------------------------
function renderStats() {
  const total = allHistory.length;
  const avg = total
    ? Math.round(
        (allHistory.reduce((sum, a) => sum + (a.overall_similarity || 0), 0) / total) * 100
      )
    : 0;
  const highest = total
    ? Math.round(Math.max(...allHistory.map((a) => a.overall_similarity || 0)) * 100)
    : 0;
  const flagged = allHistory.filter(
    (a) => (a.overall_similarity || 0) >= 0.5
  ).length;

  const stats = [
    { emoji: "🗂", num: total, cap: "Total analyses" },
    { emoji: "📊", num: avg + "%", cap: "Average similarity" },
    { emoji: "🔺", num: highest + "%", cap: "Highest similarity" },
    { emoji: "🚩", num: flagged, cap: "Flagged (≥50%)" },
  ];

  document.getElementById("historyStats").innerHTML = stats
    .map(
      (s) => `
      <div class="history-stat">
        <span class="stat-emoji" aria-hidden="true">${s.emoji}</span>
        <div>
          <div class="stat-num">${s.num}</div>
          <div class="stat-cap">${s.cap}</div>
        </div>
      </div>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// List rendering (search + sort aware)
// ---------------------------------------------------------------------------
function getVisibleHistory() {
  const query = searchQuery.trim().toLowerCase();

  let list = allHistory.filter((item) => {
    if (!query) return true;
    const refName = (item.reference_paper_name || item.reference_paper || "").toLowerCase();
    const stuName = (item.student_paper_name || item.student_paper || "").toLowerCase();
    return refName.includes(query) || stuName.includes(query);
  });

  const sorters = {
    "date-desc": (a, b) => new Date(b.timestamp) - new Date(a.timestamp),
    "date-asc": (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
    "overall-desc": (a, b) => (b.overall_similarity || 0) - (a.overall_similarity || 0),
    "overall-asc": (a, b) => (a.overall_similarity || 0) - (b.overall_similarity || 0),
  };
  list.sort(sorters[sortMode] || sorters["date-desc"]);
  return list;
}

function renderList() {
  const listEl = document.getElementById("historyList");
  const emptyEl = document.getElementById("historyEmpty");
  const countEl = document.getElementById("historyCount");
  const visible = getVisibleHistory();

  countEl.textContent = `${visible.length} of ${allHistory.length} analyses`;

  if (allHistory.length === 0) {
    listEl.innerHTML = "";
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  if (visible.length === 0) {
    listEl.innerHTML = `<div class="empty-box"><p>No analyses match “${escapeHtml(searchQuery)}”.</p></div>`;
    return;
  }

  listEl.innerHTML = visible.map(historyItemHtml).join("");

  // Wire up per-item actions
  listEl.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => openReport(btn.dataset.view));
  });
  listEl.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", () => deleteItem(btn.dataset.delete, btn.dataset.name));
  });
}

function historyItemHtml(item) {
  const overallPct = Math.round((item.overall_similarity || 0) * 100);
  const refName = item.reference_paper_name || item.reference_paper || "reference.pdf";
  const stuName = item.student_paper_name || item.student_paper || "student.pdf";
  const date = item.timestamp ? new Date(item.timestamp).toLocaleString() : "Unknown date";

  let riskBadge;
  if (overallPct > 75) riskBadge = `<span class="badge high">🚩 HIGH</span>`;
  else if (overallPct >= 50) riskBadge = `<span class="badge medium">⚠️ MEDIUM</span>`;
  else riskBadge = `<span class="badge low">✅ LOW</span>`;

  return `
    <article class="history-item">
      <div class="history-main">
        <h3 class="history-papers">
          ${escapeHtml(stuName)} <span class="vs">vs</span> ${escapeHtml(refName)}
        </h3>
        <p class="history-date">🕐 ${escapeHtml(date)}</p>
        <div class="history-badges">
          <span class="badge overall">${overallPct}% overall</span>
          ${riskBadge}
        </div>
      </div>
      <div class="history-actions">
        <button class="btn btn-primary btn-sm" data-view="${escapeHtml(item.job_id)}">View Report</button>
        <button class="btn btn-danger btn-sm" data-delete="${escapeHtml(item.job_id)}"
                data-name="${escapeHtml(stuName)}">Delete</button>
      </div>
    </article>`;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
function openReport(jobId) {
  sessionStorage.setItem("rg_job_id", jobId);
  window.location.href = "results.html";
}

async function deleteItem(jobId, paperName) {
  const confirmed = await showConfirm(
    `Delete the analysis for “${paperName}”? This cannot be undone.`,
    { title: "Delete analysis?", confirmText: "Delete" }
  );
  if (!confirmed) return;

  try {
    await apiDeleteHistoryItem(jobId);
    allHistory = allHistory.filter((a) => a.job_id !== jobId);
    renderStats();
    renderList();
    toast("Analysis deleted", "success");
  } catch (error) {
    toast(error.message || "Could not delete analysis", "error");
  }
}

// ---------------------------------------------------------------------------
// Toolbar wiring: search (with debounce), sort, clear-all
// ---------------------------------------------------------------------------
const searchInput = document.getElementById("historySearch");
searchInput.addEventListener("input", () => {
  clearTimeout(searchInput._debounce);
  searchInput._debounce = setTimeout(() => {
    searchQuery = searchInput.value;
    renderList();
  }, 200);
});

document.getElementById("historySort").addEventListener("change", (event) => {
  sortMode = event.target.value;
  renderList();
});

document.getElementById("clearHistoryBtn").addEventListener("click", async () => {
  if (allHistory.length === 0) {
    toast("History is already empty", "info");
    return;
  }
  const confirmed = await showConfirm(
    `This will permanently delete all ${allHistory.length} saved analyses. This cannot be undone.`,
    { title: "Clear all history?", confirmText: "Delete All" }
  );
  if (!confirmed) return;

  try {
    await apiClearHistory();
    allHistory = [];
    renderStats();
    renderList();
    toast("History cleared", "success");
  } catch (error) {
    toast(error.message || "Could not clear history", "error");
  }
});