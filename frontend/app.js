// app.js — Lab Report Explainer frontend logic
// Pure vanilla JS. No framework. No dependencies.
// Communicates with FastAPI at API_BASE.
 
const API_BASE = "http://gagan61-lab-report-explainer.hf.space";
 
// ── Application state ─────────────────────────────────────────────────────
// All state lives here. Never read from DOM for logic decisions.
const S = {
  patient:      { age: null, gender: null },
  flaggedTests: [],   // from /analyze — no explanations — used to re-call /explain on toggle
  tests:        [],   // full tests with explanations — what's currently rendered
  lang:         "english",
  mode:         "patient",
  chat: {
    history: [],     // [{role: "user"|"assistant", content: "..."}]
    turns:   0,      // current turn count (max 8)
    ctx:     null,   // compact JSON string of tests — sent with every chat call
  },
  mainFile:     null, // primary uploaded PDF File
  compareFile1: null, // compare: older report
  compareFile2: null, // compare: newer report
};
 
// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
 
// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupUpload();
  setupToggles();
  setupAnalyzeBtn();
  setupChat();
  setupCompare();
  setupExport();
  pingServer(); // wake up backend on page load
});
 
// Ping backend so it's warm before user hits Analyze
async function pingServer() {
  try {
    await fetch(`${API_BASE}/health`);
    $("status-dot").classList.add("active");
  } catch {
    // Server not running — show nothing, will surface on analyze
  }
}
 
// ── File upload setup ──────────────────────────────────────────────────────
function setupUpload() {
  const area = $("upload-area");
  const input = $("file-input");
 
  // Click to open file picker
  area.addEventListener("click", () => input.click());
 
  // Drag and drop
  area.addEventListener("dragover", e => {
    e.preventDefault();
    area.classList.add("drag-over");
  });
  area.addEventListener("dragleave", () => area.classList.remove("drag-over"));
  area.addEventListener("drop", e => {
    e.preventDefault();
    area.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setMainFile(file);
  });
 
  // File input change
  input.addEventListener("change", () => {
    if (input.files[0]) setMainFile(input.files[0]);
  });
}
 
function setMainFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Only PDF files are supported. Please upload a .pdf file.");
    return;
  }
  S.mainFile = file;
  $("upload-text").textContent = "File selected";
  $("upload-filename").textContent = file.name;
  $("upload-filename").classList.remove("hidden");
  $("analyze-btn").disabled = false;
}
 
// ── Toggles (language + view mode) ────────────────────────────────────────
function setupToggles() {
  // Language buttons
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".lang-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      S.lang = btn.dataset.lang;
      if (S.tests.length > 0) reExplain(); // re-generate if results exist
    });
  });
 
  // View mode buttons (patient / doctor)
  document.querySelectorAll(".view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      S.mode = btn.dataset.mode;
      if (S.tests.length > 0) reExplain();
    });
  });
}
 
// ── Analyze button ─────────────────────────────────────────────────────────
function setupAnalyzeBtn() {
  $("analyze-btn").addEventListener("click", analyzeReport);
}
 
async function analyzeReport() {
  const age    = $("age-input").value.trim();
  const gender = $("gender-input").value;
 
  if (!S.mainFile) return showError("Please upload a PDF report first.");
  if (!age || isNaN(age) || age < 1 || age > 120) return showError("Please enter a valid age (1–120).");
  if (!gender) return showError("Please select a gender.");
 
  S.patient = { age: parseInt(age), gender };
  hideError();
 
  showLoading("Reading your report…", "Gemini is extracting test values. This takes 10–30 seconds.");
 
  const formData = new FormData();
  formData.append("file", S.mainFile);
  formData.append("age", age);
  formData.append("gender", gender);
  formData.append("language", S.lang);
  formData.append("mode", S.mode);
 
  try {
    const res = await fetch(`${API_BASE}/analyze`, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    const data = await res.json();
 
    // Store flagged tests WITHOUT explanations for re-explain calls
    S.flaggedTests = data.tests.map(t => {
      const { explanation, doctor_questions, ...rest } = t;
      return rest;
    });
 
    S.tests = data.tests;
 
    // Build compact context for chat (test name + value + flag only)
    S.chat.ctx = JSON.stringify(
      data.tests.map(t => ({
        test: t.test_name,
        value: `${t.value ?? "?"} ${t.unit ?? ""}`.trim(),
        flag: t.flag,
        range: t.reference_range || `${t.ref_min ?? ""}–${t.ref_max ?? ""}`,
      }))
    );
 
    hideLoading();
    renderSummary(data);
    renderResults(data.tests);
    showSection("toggle-row");
    showSection("results-section");
    showSection("chat-section");
    showSection("export-section");
 
  } catch (err) {
    hideLoading();
    showError(`Analysis failed: ${err.message}. Check that the backend is running and try again.`);
  }
}
 
// ── Re-explain (language or view toggle) ──────────────────────────────────
async function reExplain() {
  if (!S.flaggedTests.length) return;
 
  showLoading("Updating explanations…", `Switching to ${S.mode === "doctor" ? "clinical" : "plain language"} view in ${S.lang}.`);
 
  const formData = new FormData();
  formData.append("tests", JSON.stringify(S.flaggedTests));
  formData.append("age", S.patient.age);
  formData.append("gender", S.patient.gender);
  formData.append("language", S.lang);
  formData.append("mode", S.mode);
 
  try {
    const res = await fetch(`${API_BASE}/explain`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    S.tests = data.tests;
    hideLoading();
    renderResults(data.tests);
  } catch (err) {
    hideLoading();
    showError(`Could not update explanations: ${err.message}`);
  }
}
 
// ── Render results ─────────────────────────────────────────────────────────
function renderSummary(data) {
  const tests = data.tests;
  const nTotal   = tests.length;
  const nNormal  = tests.filter(t => t.flag === "Normal").length;
  const nCaution = tests.filter(t => t.flag === "Caution").length;
  const nDanger  = tests.filter(t => t.flag === "See Doctor").length;
 
  $("stat-total").textContent   = nTotal;
  $("stat-normal").textContent  = nNormal;
  $("stat-caution").textContent = nCaution;
  $("stat-danger").textContent  = nDanger;
  showSection("results-summary");
}
 
function renderResults(tests) {
  const container = $("test-cards");
  container.innerHTML = "";
 
  // Sort: See Doctor → Caution → Normal
  const sorted = [...tests].sort((a, b) => {
    const rank = { "See Doctor": 0, "Caution": 1, "Normal": 2 };
    return (rank[a.flag] ?? 2) - (rank[b.flag] ?? 2);
  });
 
  sorted.forEach(test => container.appendChild(buildCard(test)));
  renderDoctorQuestions(tests);
}
 
function buildCard(test) {
  const flagClass = flagToClass(test.flag);
  const card = document.createElement("div");
  card.className = `test-card ${flagClass}`;
 
  const refStr = test.reference_range ||
    ((test.ref_min !== null && test.ref_max !== null)
      ? `${test.ref_min}–${test.ref_max}`
      : test.ref_min != null ? `>${test.ref_min}`
      : test.ref_max != null ? `<${test.ref_max}`
      : "—");
 
  const valueStr = test.value !== null && test.value !== undefined
    ? `${test.value} ${test.unit || ""}`.trim()
    : "—";
 
  const qs = (test.doctor_questions || []).filter(Boolean);
 
  card.innerHTML = `
    <div class="card-header">
      <span class="test-name">${escHtml(test.test_name)}</span>
      ${buildBadge(test.flag)}
    </div>
    <div class="value-row">
      <span class="value">${escHtml(valueStr)}</span>
      <span class="ref-label">Ref: ${escHtml(refStr)}</span>
    </div>
    <div class="gauge-track">
      <div class="gauge-fill ${flagClass}" style="width: ${test.gauge_pct ?? 0}%"></div>
    </div>
    ${test.explanation ? `
      <p class="explanation${S.mode === "doctor" ? " doctor-mode" : ""}">${escHtml(test.explanation)}</p>
    ` : ""}
    ${qs.length ? `
      <div class="doctor-q-inline">
        <span class="q-label">Ask your doctor:</span>
        <ul>${qs.map(q => `<li>${escHtml(q)}</li>`).join("")}</ul>
      </div>
    ` : ""}
  `;
 
  return card;
}
 
function buildBadge(flag) {
  const cls = { "Normal": "badge-normal", "Caution": "badge-caution", "See Doctor": "badge-danger" };
  return `<span class="status-badge ${cls[flag] || "badge-normal"}">${escHtml(flag)}</span>`;
}
 
function flagToClass(flag) {
  return { "Normal": "normal", "Caution": "caution", "See Doctor": "see-doctor" }[flag] || "normal";
}
 
function renderDoctorQuestions(tests) {
  const allQs = [];
  tests.forEach(t => {
    (t.doctor_questions || []).filter(Boolean).forEach(q => {
      allQs.push({ test: t.test_name, q });
    });
  });
 
  const card = $("doctor-questions-card");
  const list = $("doctor-q-list");
 
  if (!allQs.length) {
    card.classList.add("hidden");
    return;
  }
 
  list.innerHTML = allQs.map(({ test, q }) => `
    <li>
      <span class="q-test-tag">${escHtml(test)}</span>
      <span>${escHtml(q)}</span>
    </li>
  `).join("");
 
  card.classList.remove("hidden");
}
 
// ── Chat ───────────────────────────────────────────────────────────────────
function setupChat() {
  const input   = $("chat-input");
  const sendBtn = $("send-btn");
 
  sendBtn.addEventListener("click", sendChat);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
}
 
async function sendChat() {
  const input = $("chat-input");
  const msg = input.value.trim();
  if (!msg || S.chat.turns >= 8) return;
  if (!S.chat.ctx) return showError("Please analyze a report before using the chat.");
 
  input.value = "";
  appendBubble("user", msg);
  S.chat.turns++;
  updateTurnsNote();
 
  // Disable input at limit
  if (S.chat.turns >= 8) {
    input.disabled = true;
    input.placeholder = "Chat limit reached. Refresh to start a new session.";
    $("send-btn").disabled = true;
  }
 
  // Show thinking state
  const thinkingEl = appendBubble("ai", "Thinking…");
  thinkingEl.classList.add("thinking");
 
  const formData = new FormData();
  formData.append("message", msg);
  formData.append("report_context", S.chat.ctx);
  formData.append("history", JSON.stringify(S.chat.history));
  formData.append("age", S.patient.age);
  formData.append("gender", S.patient.gender);
  formData.append("language", S.lang);
 
  try {
    const res = await fetch(`${API_BASE}/chat`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
 
    thinkingEl.classList.remove("thinking");
    thinkingEl.textContent = data.reply;
 
    S.chat.history.push({ role: "user", content: msg });
    S.chat.history.push({ role: "assistant", content: data.reply });
 
  } catch (err) {
    thinkingEl.textContent = "Sorry, something went wrong. Please try again.";
    thinkingEl.classList.remove("thinking");
  }
}
 
function appendBubble(role, text) {
  const msgs = $("chat-messages");
  const el = document.createElement("div");
  el.className = `bubble bubble-${role}`;
  el.textContent = text;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
  return el;
}
 
function updateTurnsNote() {
  const note = $("chat-turns-note");
  const remaining = 8 - S.chat.turns;
  note.textContent = remaining > 0
    ? `${remaining} question${remaining === 1 ? "" : "s"} remaining in this session`
    : "Chat limit reached.";
}
 
// ── Compare ────────────────────────────────────────────────────────────────
function setupCompare() {
  const area1  = $("compare-area1");
  const input1 = $("compare-file1");
  const area2  = $("compare-area2");
  const input2 = $("compare-file2");
 
  setupCompareUpload(area1, input1, 1);
  setupCompareUpload(area2, input2, 2);
 
  $("compare-btn").addEventListener("click", compareReports);
}
 
function setupCompareUpload(area, input, num) {
  area.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError("Compare: please upload PDF files only.");
      return;
    }
    if (num === 1) S.compareFile1 = file;
    else           S.compareFile2 = file;
    area.textContent = file.name;
    area.classList.add("has-file");
    checkCompareReady();
  });
}
 
function checkCompareReady() {
  $("compare-btn").disabled = !(S.compareFile1 && S.compareFile2);
}
 
async function compareReports() {
  if (!S.compareFile1 || !S.compareFile2) return;
  const age    = $("age-input").value || S.patient.age;
  const gender = $("gender-input").value || S.patient.gender;
 
  showLoading("Comparing reports…", "Extracting both reports. This may take 30–60 seconds.");
 
  const formData = new FormData();
  formData.append("file1", S.compareFile1);
  formData.append("file2", S.compareFile2);
  formData.append("age", age);
  formData.append("gender", gender);
 
  try {
    const res = await fetch(`${API_BASE}/compare`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    hideLoading();
    renderComparison(data);
    showSection("compare-results");
  } catch (err) {
    hideLoading();
    showError(`Comparison failed: ${err.message}`);
  }
}
 
function renderComparison(data) {
  const { diff, summary } = data;
 
  $("cmp-improved").textContent = summary.improved;
  $("cmp-worsened").textContent = summary.worsened;
  $("cmp-stable").textContent   = summary.stable;
 
  const tbody = $("compare-tbody");
  tbody.innerHTML = diff.map(row => {
    const chip = buildChip(row.change);
    const oldVal = row.old_value !== null ? `${row.old_value} ${row.old_unit || ""}`.trim() : "—";
    const newVal = row.new_value !== null ? `${row.new_value} ${row.new_unit || ""}`.trim() : "—";
    return `
      <tr class="${escHtml(row.change)}">
        <td>${escHtml(row.test_name)}</td>
        <td>${escHtml(oldVal)}</td>
        <td>${escHtml(newVal)}</td>
        <td>${escHtml(row.old_flag || "—")}</td>
        <td>${escHtml(row.new_flag || "—")}</td>
        <td>${chip}</td>
      </tr>
    `;
  }).join("");
}
 
function buildChip(change) {
  const labels = { improved: "Improved", worsened: "Worsened", stable: "Stable", new: "New", missing: "Missing" };
  const cls    = { improved: "chip-improved", worsened: "chip-worsened", stable: "chip-stable", new: "chip-new", missing: "chip-missing" };
  return `<span class="change-chip ${cls[change] || ""}">${labels[change] || change}</span>`;
}
 
// ── Export ─────────────────────────────────────────────────────────────────
function setupExport() {
  $("export-btn").addEventListener("click", exportPDF);
}
 
async function exportPDF() {
  if (!S.tests.length) return;
 
  $("export-btn").disabled = true;
  $("export-btn").textContent = "Generating PDF…";
 
  const formData = new FormData();
  formData.append("tests", JSON.stringify(S.tests));
  formData.append("age", S.patient.age);
  formData.append("gender", S.patient.gender);
 
  try {
    const res = await fetch(`${API_BASE}/export`, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
 
    // Trigger file download
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "lab-report-summary.pdf";
    a.click();
    URL.revokeObjectURL(url);
 
  } catch (err) {
    showError(`Export failed: ${err.message}`);
  } finally {
    $("export-btn").disabled = false;
    $("export-btn").textContent = "Download report as PDF";
  }
}
 
// ── UI helpers ─────────────────────────────────────────────────────────────
function showLoading(text, sub = "") {
  $("loading-text").textContent = text;
  $("loading-sub").textContent  = sub;
  $("loading-overlay").classList.remove("hidden");
}
 
function hideLoading() {
  $("loading-overlay").classList.add("hidden");
}
 
function showError(msg) {
  const el = $("error-banner");
  el.textContent = msg;
  el.classList.remove("hidden");
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}
 
function hideError() {
  $("error-banner").classList.add("hidden");
}
 
function showSection(id) {
  const el = $(id);
  if (el) el.classList.remove("hidden");
}
 
// Escape HTML to prevent XSS from API data
function escHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
 