/*
   results.js — Similarity report dashboard.
   Loads the real analysis JSON from the backend (/api/results) and renders
   every number you see. Nothing is hardcoded.

   Interactive features: risk filter tabs, sorting, canvas distribution
   histogram, animated donut + counters, JSON export, print, copy to clipboard.
*/

// State for the interactive dashboard
let allMatches = [];
let currentFilter = "ALL";
let currentSort = "combined-desc";
let currentReport = null;

document.addEventListener("DOMContentLoaded", loadResults);

async function loadResults() {
  const loading = document.getElementById("resultsLoading");
  const empty = document.getElementById("resultsEmpty");
  const content = document.getElementById("resultsContent");

  try {
    const jobId = sessionStorage.getItem("rg_job_id");
    sessionStorage.removeItem("rg_job_id");

    const data = jobId
      ? await apiGetResultsById(jobId)
      : await apiGetResults();

    currentReport = data;
    loading.hidden = true;
    content.hidden = false;
    renderResults(data);
    setupDashboardControls(data);
  } catch (error) {
    loading.hidden = true;
    empty.hidden = false;
  }
}

function renderResults(data) {
  const overall = data.overall_similarity || 0;
  const overallPct = Math.round(overall * 100);

  // --- Report meta line ---
  const refName = data.reference_paper_name || data.reference_paper || "reference.pdf";
  const stuName = data.student_paper_name || data.student_paper || "student.pdf";
  const stamp = data.timestamp ? new Date(data.timestamp).toLocaleString() : "";
  document.getElementById("reportMeta").textContent =
    `${stuName}  vs  ${refName}${stamp ? "  •  " + stamp : ""}`;

  // --- Summary cards (animated counters) ---
  animateNumber("overallValue", overallPct, "%");
  animateDonut("overallDonut", overallPct);

  const overallChip = document.getElementById("overallClass");
  if (overallPct > 75) {
    overallChip.textContent = "High similarity";
    overallChip.className = "risk-chip high";
  } else if (overallPct >= 50) {
    overallChip.textContent = "Moderate similarity";
    overallChip.className = "risk-chip medium";
  } else {
    overallChip.textContent = "Low similarity";
    overallChip.className = "risk-chip low";
  }

  animateNumber("highCount", data.high_similarity_matches ?? 0);
  animateNumber("mediumCount", data.medium_similarity_matches ?? 0);
  animateNumber("lowCount", data.low_similarity_matches ?? 0);

  // --- Breakdown bars ---
  animateBar("semanticBar", "semanticValue", data.semantic_similarity ?? 0);
  animateBar("lexicalBar", "lexicalValue", data.lexical_similarity ?? 0);
  animateBar("combinedBar", "combinedValue", data.combined_similarity ?? 0);

  document.getElementById("breakdownNote").textContent =
    `Average best-match scores across all ${data.student_chunk_count ?? "?"} student chunks vs ` +
    `${data.reference_chunk_count ?? "?"} reference chunks. ` +
    `Combined score = ${(data.weights?.semantic_weight ?? 0.7) * 10}/10 semantic + ` +
    `${(data.weights?.lexical_weight ?? 0.3) * 10}/10 lexical.`;

  // --- Store matches and render them with the toolbar ---
  allMatches = data.top_matches || [];
  document.getElementById("matchCountChip").textContent = `Top ${allMatches.length} matches`;
  renderMatchList();

  // --- Histogram of match scores ---
  drawDistributionChart(allMatches);
}

// ---------------------------------------------------------------------------
// Match list rendering (filter + sort aware)
// ---------------------------------------------------------------------------
function getFilteredMatches() {
  let list = allMatches.filter((m) => currentFilter === "ALL" || m.risk === currentFilter);

  const sorters = {
    "combined-desc": (a, b) => (b.combined_similarity || 0) - (a.combined_similarity || 0),
    "combined-asc": (a, b) => (a.combined_similarity || 0) - (b.combined_similarity || 0),
    "semantic-desc": (a, b) => (b.semantic_similarity || 0) - (a.semantic_similarity || 0),
    "lexical-desc": (a, b) => (b.lexical_similarity || 0) - (a.lexical_similarity || 0),
    "page-asc": (a, b) => (a.student_page || 0) - (b.student_page || 0),
  };
  list.sort(sorters[currentSort] || sorters["combined-desc"]);
  return list;
}

function renderMatchList() {
  const list = document.getElementById("matchList");
  const noMatches = document.getElementById("noMatchesMessage");
  const matches = getFilteredMatches();

  // Update counts on filter tabs
  document.querySelectorAll("#filterTabs .filter-tab").forEach((tab) => {
    const key = tab.dataset.filter;
    const count = key === "ALL"
      ? allMatches.length
      : allMatches.filter((m) => m.risk === key).length;
    let label = tab.textContent.replace(/\s*\(?\d*\)?$/, "").trim();
    tab.innerHTML = `${escapeHtml(label)} <span class="count">${count}</span>`;
  });

  if (matches.length === 0) {
    list.innerHTML = "";
    noMatches.hidden = false;
    return;
  }
  noMatches.hidden = true;

  list.innerHTML = matches.map((m, i) => matchCardHtml(m, i)).join("");

  list.querySelectorAll("[data-match-index]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openMatchModal(matches[Number(btn.dataset.matchIndex)], matches);
    });
  });
}

/** Wire up filter tabs, sort select, export + print buttons. */
function setupDashboardControls(data) {
  document.querySelectorAll("#filterTabs .filter-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#filterTabs .filter-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter = tab.dataset.filter;
      renderMatchList();
    });
  });

  document.getElementById("sortSelect").addEventListener("change", (event) => {
    currentSort = event.target.value;
    renderMatchList();
  });

  const exportBtn = document.getElementById("exportJsonBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      const name = (data.student_paper_name || "report").replace(/\.pdf$/i, "");
      downloadJson(data, `similarity-report-${name}.json`);
      toast("Report exported as JSON", "success");
    });
  }

  const printBtn = document.getElementById("printBtn");
  if (printBtn) {
    printBtn.addEventListener("click", () => window.print());
  }
}

// ---------------------------------------------------------------------------
// Canvas histogram: how many matches per similarity range
// ---------------------------------------------------------------------------
function drawDistributionChart(matches) {
  const canvas = document.getElementById("distributionChart");
  if (!canvas) return;

  const ranges = [
    { label: "0–20%", min: 0, max: 0.2, color: "#22c55e" },
    { label: "20–40%", min: 0.2, max: 0.4, color: "#4ade80" },
    { label: "40–60%", min: 0.4, max: 0.6, color: "#f59e0b" },
    { label: "60–80%", min: 0.6, max: 0.8, color: "#f97316" },
    { label: "80–100%", min: 0.8, max: 1.01, color: "#ef4444" },
  ];

  const counts = ranges.map(
    (r) => matches.filter((m) => {
      const v = m.combined_similarity || 0;
      return v >= r.min && v < r.max;
    }).length
  );

  function draw() {
    const parent = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const cssW = parent.clientWidth || 600;
    const cssH = parent.clientHeight || 220;

    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";

    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssW, cssH);

    const padding = { top: 20, right: 14, bottom: 34, left: 34 };
    const plotW = cssW - padding.left - padding.right;
    const plotH = cssH - padding.top - padding.bottom;
    const maxCount = Math.max(1, ...counts);
    const slot = plotW / ranges.length;
    const barW = Math.min(64, slot * 0.6);
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const gridColor = dark ? "rgba(148,163,184,0.25)" : "rgba(100,116,139,0.25)";
    const textColor = dark ? "#97a3ba" : "#64748b";

    // horizontal gridlines + y labels
    ctx.font = "11px 'Segoe UI', sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const steps = Math.min(maxCount, 4);
    for (let i = 0; i <= steps; i++) {
      const value = Math.round((maxCount / steps) * i);
      const y = padding.top + plotH - (value / maxCount) * plotH;
      ctx.strokeStyle = gridColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + plotW, y);
      ctx.stroke();
      ctx.fillStyle = textColor;
      ctx.fillText(String(value), padding.left - 6, y);
    }

    // bars (animated growth)
    ranges.forEach((range, i) => {
      const count = counts[i];
      const targetH = (count / maxCount) * plotH;
      const x = padding.left + slot * i + (slot - barW) / 2;
      const finalY = padding.top + plotH - targetH;

      // animate with a tween using rAF
      const start = performance.now();
      const duration = 700;
      function grow(now) {
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        const h = targetH * eased;
        const y = padding.top + plotH - h;

        const grad = ctx.createLinearGradient(0, y, 0, padding.top + plotH);
        grad.addColorStop(0, range.color);
        grad.addColorStop(1, range.color + "55");
        ctx.fillStyle = grad;
        ctx.beginPath();
        const radius = Math.min(8, h / 2);
        ctx.roundRect ? ctx.roundRect(x, y, barW, Math.max(h, 0), radius)
                      : ctx.rect(x, y, barW, Math.max(h, 0));
        ctx.fill();

        if (p < 1) {
          // clear just this bar's column area then redraw
          requestAnimationFrame(grow);
        } else {
          // count label above the bar
          if (count > 0) {
            ctx.fillStyle = textColor;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.font = "600 12px 'Segoe UI', sans-serif";
            ctx.fillText(String(count), x + barW / 2, finalY - 4);
          }
        }
      }
      requestAnimationFrame(grow);
    });

    // x labels
    ctx.fillStyle = textColor;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.font = "11px 'Segoe UI', sans-serif";
    ranges.forEach((range, i) => {
      const x = padding.left + slot * i + slot / 2;
      ctx.fillText(range.label, x, padding.top + plotH + 8);
    });
  }

  draw();
  let resizeT;
  window.addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(draw, 200);
  });
}

// ---------------------------------------------------------------------------
// Small animation helpers
// ---------------------------------------------------------------------------
/** Fill a progress bar + its % label with a small animation. */
function animateBar(barId, valueId, score) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const bar = document.getElementById(barId);
  const label = document.getElementById(valueId);
  label.textContent = pct + "%";
  requestAnimationFrame(() => {
    bar.style.width = pct + "%";
  });
}

/** Count from 0 up to target inside an element. */
function animateNumber(elementId, target, suffix = "") {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = target + suffix;
    return;
  }
  const start = performance.now();
  const duration = 900;
  function tick(now) {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * eased) + suffix;
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

/** Animate the conic-gradient donut from 0% to target. */
function animateDonut(donutId, targetPct) {
  const donut = document.getElementById(donutId);
  if (!donut) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    donut.style.setProperty("--pct", targetPct);
    donut.style.background =
      `conic-gradient(var(--primary) ${targetPct}%, var(--border) 0)`;
    return;
  }
  const start = performance.now();
  const duration = 1000;
  function tick(now) {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    const pct = Math.round(targetPct * eased);
    donut.style.setProperty("--pct", pct);
    donut.style.background =
      `conic-gradient(var(--primary) ${pct}%, var(--border) 0)`;
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function matchCardHtml(match, index) {
  const combinedPct = Math.round((match.combined_similarity || 0) * 100);
  return `
    <article class="match-card risk-${match.risk}">
      <div class="match-head">
        <h3 class="match-title">Match #${index + 1} — ${riskText(match.risk)}</h3>
        <span class="match-combined">${combinedPct}%</span>
      </div>
      <div class="match-score-row">
        <span>Semantic: <strong>${formatPercent(match.semantic_similarity)}</strong></span>
        <span>Lexical: <strong>${formatPercent(match.lexical_similarity)}</strong></span>
        <span>Combined: <strong>${formatPercent(match.combined_similarity)}</strong></span>
      </div>
      <div class="compare-preview">
        <div class="compare-box student">
          <h4>Student paper — page ${match.student_page}</h4>
          <p>${escapeHtml(match.student_text)}</p>
        </div>
        <div class="compare-box reference">
          <h4>Reference paper — page ${match.reference_page}</h4>
          <p>${escapeHtml(match.reference_text)}</p>
        </div>
      </div>
      <div class="match-footer">
        <button class="btn btn-outline btn-sm" data-match-index="${index}">View details</button>
      </div>
    </article>`;
}

// ---------------------------------------------------------------------------
// Detail modal (with copy-to-clipboard)
// ---------------------------------------------------------------------------
const modal = document.getElementById("matchModal");
let currentModalMatch = null;

function openMatchModal(match, allFiltered) {
  currentModalMatch = match;

  document.getElementById("modalTitle").textContent =
    `Match #${match.student_chunk_id} → Reference #${match.reference_chunk_id}`;

  document.getElementById("modalScores").innerHTML = `
    <div class="score-pill"><div class="val">${formatPercent(match.semantic_similarity)}</div><div class="lbl">Semantic</div></div>
    <div class="score-pill"><div class="val">${formatPercent(match.lexical_similarity)}</div><div class="lbl">Lexical</div></div>
    <div class="score-pill"><div class="val">${formatPercent(match.combined_similarity)}</div><div class="lbl">Combined</div></div>
    <div class="score-pill"><div class="val">${match.risk}</div><div class="lbl">Risk level</div></div>`;

  document.getElementById("modalStudentPage").textContent = `Page ${match.student_page}`;
  document.getElementById("modalReferencePage").textContent = `Page ${match.reference_page}`;

  // Highlight words the two texts share (display aid only)
  document.getElementById("modalStudentText").innerHTML = highlightSharedWords(
    match.student_text, match.reference_text
  );
  document.getElementById("modalReferenceText").innerHTML = highlightSharedWords(
    match.reference_text, match.student_text
  );

  modal.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeMatchModal() {
  modal.hidden = true;
  document.body.style.overflow = "";
  currentModalMatch = null;
}

document.getElementById("modalClose").addEventListener("click", closeMatchModal);
modal.addEventListener("click", (event) => {
  if (event.target === modal) closeMatchModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.hidden) closeMatchModal();
});

// Copy both matched texts to the clipboard
const copyBtn = document.getElementById("copyMatchBtn");
if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    if (!currentModalMatch) return;
    const text =
      `STUDENT PAPER (page ${currentModalMatch.student_page}):\n${currentModalMatch.student_text}\n\n` +
      `REFERENCE PAPER (page ${currentModalMatch.reference_page}):\n${currentModalMatch.reference_text}`;
    try {
      await navigator.clipboard.writeText(text);
      toast("Matched texts copied to clipboard", "success");
    } catch (err) {
      toast("Clipboard unavailable in this browser", "warning");
    }
  });
}