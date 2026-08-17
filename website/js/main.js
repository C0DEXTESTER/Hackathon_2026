/*
   main.js — Shared behavior on every page:
   dark/light theme • mobile menu • scroll reveal • hero particles •
   typing effect • animated counters • toasts • confirm dialog •
   scroll-to-top • button ripples • navbar shrink + helpers.
*/

// ---------------------------------------------------------------------------
// 1. MOBILE HAMBURGER MENU
// ---------------------------------------------------------------------------
const navToggle = document.getElementById("navToggle");
const navMenu = document.getElementById("navMenu");

if (navToggle && navMenu) {
  navToggle.addEventListener("click", () => {
    const isOpen = navMenu.classList.toggle("open");
    navToggle.classList.toggle("open", isOpen);
    navToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });

  navMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navMenu.classList.remove("open");
      navToggle.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });

  // Close when clicking outside the menu
  document.addEventListener("click", (event) => {
    if (!navMenu.contains(event.target) && !navToggle.contains(event.target)) {
      navMenu.classList.remove("open");
      navToggle.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
    }
  });
}

// ---------------------------------------------------------------------------
// 2. DARK / LIGHT THEME (saved in localStorage)
// ---------------------------------------------------------------------------
const THEME_KEY = "rg_theme";

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}
(function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
})();

const themeToggle = document.getElementById("themeToggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem(THEME_KEY, next);
    toast(
      next === "dark" ? "🌙 Dark mode enabled" : "☀️ Light mode enabled",
      "info"
    );
  });
}

// ---------------------------------------------------------------------------
// 3. SCROLL-REVEAL — elements with [data-reveal] fade in when visible
// ---------------------------------------------------------------------------
const revealObserver = "IntersectionObserver" in window
  ? new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -30px 0px" }
    )
  : null;

document.querySelectorAll("[data-reveal]").forEach((el) => {
  if (revealObserver) {
    if (el.dataset.revealDelay) {
      el.style.setProperty("--reveal-delay", el.dataset.revealDelay);
    }
    revealObserver.observe(el);
  } else {
    el.classList.add("revealed"); // very old browser: just show it
  }
});

// ---------------------------------------------------------------------------
// 4. HERO PARTICLE CONSTELLATION (canvas, home page only)
// ---------------------------------------------------------------------------
(function heroParticles() {
  const canvas = document.getElementById("heroCanvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let particles = [];
  let width = 0;
  let height = 0;
  let rafId = null;

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    width = canvas.width = Math.max(1, Math.floor(rect.width));
    height = canvas.height = Math.max(1, Math.floor(rect.height));
    spawn();
  }

  function spawn() {
    const count = Math.min(70, Math.floor((width * height) / 16000));
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: 1 + Math.random() * 2,
    }));
  }

  function isDark() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  function frame() {
    ctx.clearRect(0, 0, width, height);
    const dark = isDark();
    const dotColor = dark ? "rgba(165,180,252," : "rgba(79,70,229,";
    const lineColor = dark ? "rgba(125,211,252," : "rgba(14,165,233,";

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;
    }

    // connecting lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i];
        const b = particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 110) {
          ctx.strokeStyle = lineColor + (0.16 * (1 - dist / 110)).toFixed(3) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // dots
    for (const p of particles) {
      ctx.fillStyle = dotColor + "0.55)";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }

    rafId = requestAnimationFrame(frame);
  }

  window.addEventListener("resize", resize);
  resize();

  if (reduceMotion) {
    // Draw one static frame for users who prefer reduced motion
    const once = () => {
      cancelAnimationFrame(rafId);
      frame();
      cancelAnimationFrame(rafId);
    };
    once();
  } else {
    frame();
  }

  // Pause when tab is hidden (saves battery)
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      cancelAnimationFrame(rafId);
    } else if (!reduceMotion) {
      frame();
    }
  });
})();

// ---------------------------------------------------------------------------
// 5. TYPING EFFECT (hero subtitle, home page only)
// ---------------------------------------------------------------------------
(function typingEffect() {
  const el = document.getElementById("typedSubtitle");
  if (!el) return;

  const phrases = [
    "Detect duplicate and semantically similar research content using AI-powered text embeddings.",
    "Catch paraphrased content that word-matching tools miss.",
    "Runs 100% locally — your papers never leave your computer.",
  ];

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = phrases[0];
    return;
  }

  const caret = document.createElement("span");
  caret.className = "type-caret";

  let phraseIndex = 0;
  let charIndex = 0;
  let deleting = false;

  function tick() {
    const phrase = phrases[phraseIndex];
    charIndex += deleting ? -1 : 1;
    el.textContent = phrase.slice(0, charIndex);
    el.appendChild(caret);

    let delay = deleting ? 18 : 34;

    if (!deleting && charIndex === phrase.length) {
      delay = 2600; // hold the full sentence
      deleting = true;
    } else if (deleting && charIndex === 0) {
      deleting = false;
      phraseIndex = (phraseIndex + 1) % phrases.length;
      delay = 500;
    }
    setTimeout(tick, delay);
  }
  tick();
})();

// ---------------------------------------------------------------------------
// 6. ANIMATED COUNTERS — any element with [data-count]
// ---------------------------------------------------------------------------
function animateCounters(root = document) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    if (el.dataset.counted) return;
    el.dataset.counted = "1";

    const target = parseFloat(el.dataset.count) || 0;
    const suffix = el.dataset.suffix || "";
    const duration = 1400;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = target + suffix;
      return;
    }

    const start = performance.now();
    function step(now) {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}
animateCounters();

const counterObserver = "IntersectionObserver" in window
  ? new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          animateCounters(e.target.parentElement || e.target);
          counterObserver.unobserve(e.target);
        }
      });
    })
  : null;

// ---------------------------------------------------------------------------
// 7. TOAST NOTIFICATIONS — toast("message", "success" | "error" | "warning" | "info")
// ---------------------------------------------------------------------------
function ensureToastStack() {
  let stack = document.querySelector(".toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    document.body.appendChild(stack);
  }
  return stack;
}

const TOAST_ICONS = {
  success: "✅",
  error: "⛔",
  warning: "⚠️",
  info: "💡",
};

function toast(message, type = "info", duration = 3200) {
  const stack = ensureToastStack();
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", "status");
  el.innerHTML = `<span class="toast-icon">${TOAST_ICONS[type] || TOAST_ICONS.info}</span><span>${escapeHtml(message)}</span>`;
  stack.appendChild(el);

  // Limit to 4 toasts at once
  while (stack.children.length > 4) stack.firstChild.remove();

  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, duration);
}

// ---------------------------------------------------------------------------
// 8. CUSTOM CONFIRM DIALOG — showConfirm(message) returns a Promise<boolean>
//    (replaces ugly window.confirm)
// ---------------------------------------------------------------------------
function showConfirm(message, { title = "Are you sure?", confirmText = "Confirm", danger = true } = {}) {
  return new Promise((resolve) => {
    let overlay = document.getElementById("confirmModal");

    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "modal-overlay";
      overlay.id = "confirmModal";
      overlay.innerHTML = `
        <div class="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
          <div class="modal-head">
            <h2 id="confirmTitle">${escapeHtml(title)}</h2>
            <button class="modal-close" id="confirmX" aria-label="Close">&times;</button>
          </div>
          <div class="modal-body">
            <p class="confirm-text" id="confirmMsg"></p>
            <div class="confirm-actions">
              <button class="btn btn-outline btn-sm" id="confirmCancel">Cancel</button>
              <button class="btn btn-sm ${danger ? "btn-danger" : "btn-primary"}" id="confirmOk"></button>
            </div>
          </div>
        </div>`;
      document.body.appendChild(overlay);
    }

    const titleEl = overlay.querySelector("#confirmTitle");
    const msgEl = overlay.querySelector("#confirmMsg");
    const okBtn = overlay.querySelector("#confirmOk");
    const cancelBtn = overlay.querySelector("#confirmCancel");
    const closeBtn = overlay.querySelector("#confirmX");

    titleEl.textContent = title;
    msgEl.textContent = message;
    okBtn.textContent = confirmText;
    okBtn.className = `btn btn-sm ${danger ? "btn-danger" : "btn-primary"}`;

    overlay.hidden = false;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    okBtn.focus();

    function close(result) {
      overlay.hidden = true;
      document.body.style.overflow = previousOverflow;
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      closeBtn.removeEventListener("click", onCancel);
      overlay.removeEventListener("click", onOverlay);
      document.removeEventListener("keydown", onKey);
      resolve(result);
    }
    const onOk = () => close(true);
    const onCancel = () => close(false);
    const onOverlay = (e) => { if (e.target === overlay) close(false); };
    const onKey = (e) => { if (e.key === "Escape") close(false); };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    closeBtn.addEventListener("click", onCancel);
    overlay.addEventListener("click", onOverlay);
    document.addEventListener("keydown", onKey);
  });
}

// ---------------------------------------------------------------------------
// 9. SCROLL-TO-TOP BUTTON + NAVBAR SHRINK
// ---------------------------------------------------------------------------
(function scrollFeatures() {
  const btn = document.createElement("button");
  btn.className = "scroll-top";
  btn.innerHTML = "↑";
  btn.setAttribute("aria-label", "Scroll back to top");
  btn.title = "Back to top";
  document.body.appendChild(btn);

  const navbar = document.querySelector(".navbar");

  const onScroll = () => {
    const y = window.scrollY;
    btn.classList.toggle("visible", y > 400);
    if (navbar) navbar.classList.toggle("scrolled", y > 20);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();

// ---------------------------------------------------------------------------
// 10. BUTTON RIPPLE EFFECT
// ---------------------------------------------------------------------------
document.addEventListener("click", (event) => {
  const btn = event.target.closest(".btn");
  if (!btn || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const ripple = document.createElement("span");
  ripple.className = "ripple";
  ripple.style.width = ripple.style.height = size + "px";
  ripple.style.left = event.clientX - rect.left - size / 2 + "px";
  ripple.style.top = event.clientY - rect.top - size / 2 + "px";
  btn.appendChild(ripple);
  ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
});

// ---------------------------------------------------------------------------
// 11. SHARED HELPERS used by analyze.js / results.js / history.js
// ---------------------------------------------------------------------------

/** Turn 0.788 -> "78.8%" */
function formatPercent(value) {
  return (value * 100).toFixed(1) + "%";
}

/** Human readable file size: 15360 -> "15 KB" */
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

/** Risk label text (never "plagiarism" — similarity is not proof). */
function riskText(risk) {
  if (risk === "HIGH") return "High similarity — Review recommended";
  if (risk === "MEDIUM") return "Moderate similarity — Further review suggested";
  return "Low similarity";
}

/** Escape text so it can be safely inserted as HTML. */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

/**
 * Build an HTML paragraph where words shared between the student and
 * reference texts are highlighted with <mark>.
 * (Display-only highlighting — the AI scores always come from Python.)
 */
function highlightSharedWords(textA, textB, minLength = 4) {
  const wordsB = new Set(
    (textB || "").toLowerCase().match(/[a-z0-9']+/g) || []
  );

  return (textA || "")
    .split(/(\s+)/)
    .map((piece) => {
      if (/^\s+$/.test(piece)) return piece;
      const clean = piece.toLowerCase().replace(/[^a-z0-9']/g, "");
      if (clean.length >= minLength && wordsB.has(clean)) {
        return `<mark>${escapeHtml(piece)}</mark>`;
      }
      return escapeHtml(piece);
    })
    .join("");
}

/** Download any object as a pretty-printed JSON file. */
function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}