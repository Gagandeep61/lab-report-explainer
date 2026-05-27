// app.js — Lab Report Explainer frontend
// Fixes applied:
//   - CHAT_TURN_LIMIT constant (single source of truth)
//   - chat turns increment on success only (not on error)
//   - aria-pressed updated on toggle clicks
//   - keyboard Enter/Space handlers for upload areas
//   - gauge_pct clamped to 0-100
//   - hideError() called at start of compareReports and exportPDF
//   - reExplain debounced to prevent race condition
//   - Full hybrid preset system (JSON presets + PDF download links)

const API_BASE = "https://lab-report-explainer-phi.vercel.app".replace(/\/$/, "");
// If running backend locally: const API_BASE = "http://localhost:8000";

// FIX: single constant — previously 8 was hardcoded in 3 different places
const CHAT_TURN_LIMIT = 8;

// ── State ─────────────────────────────────────────────────────────────────────
const S = {
  tests:        [],
  flaggedTests: [],
  patient:      { age: 30, gender: "male" },
  mainFile:     null,
  presetActive: false,
  lang:         "english",
  mode:         "patient",
  chat: {
    turns: 0,
    ctx:   "",
    history: [],
  },
  compareFile1: null,
  compareFile2: null,
};

// ── Sample presets (JSON — no API call needed) ────────────────────────────────

const SAMPLE_PRESETS = {
  healthy: {
    label:   "Healthy Adult (Priya, 25F)",
    patient: { age: 25, gender: "female" },
    tests: [
      { test_name:"Haemoglobin", value:13.2, unit:"g/dL", reference_range:"12.0 - 15.5", ref_min:12.0, ref_max:15.5, flag:"Normal", gauge_pct:71,
        explanation:"Haemoglobin is the protein in red blood cells that carries oxygen throughout your body. Your level of 13.2 g/dL is well within the healthy range, meaning your blood is delivering oxygen efficiently.",
        doctor_questions:[] },
      { test_name:"Total WBC Count", value:7200, unit:"cells/cumm", reference_range:"4000 - 11000", ref_min:4000, ref_max:11000, flag:"Normal", gauge_pct:55,
        explanation:"White blood cells are your body's defence system that fights infections. A count of 7200 cells/cumm is normal, indicating a healthy and well-functioning immune system.",
        doctor_questions:[] },
      { test_name:"Platelet Count", value:2.80, unit:"Lacs/cumm", reference_range:"1.50 - 4.50", ref_min:1.50, ref_max:4.50, flag:"Normal", gauge_pct:52,
        explanation:"Platelets are tiny blood cells that help your blood clot when you have a cut. Your count of 2.80 Lacs/cumm is normal, meaning your blood's clotting ability is working well.",
        doctor_questions:[] },
      { test_name:"Fasting Blood Glucose", value:88, unit:"mg/dL", reference_range:"70 - 100", ref_min:70, ref_max:100, flag:"Normal", gauge_pct:73,
        explanation:"Fasting blood glucose measures sugar in your blood after not eating overnight. At 88 mg/dL your level is comfortably within the healthy range, showing good blood sugar control.",
        doctor_questions:[] },
      { test_name:"HbA1c (Glycosylated Haemoglobin)", value:5.1, unit:"%", reference_range:"4.0 - 5.6", ref_min:4.0, ref_max:5.6, flag:"Normal", gauge_pct:76,
        explanation:"HbA1c reflects your average blood sugar level over the past 2–3 months. Your level of 5.1% is well within the normal range, confirming your blood sugar has been consistently healthy.",
        doctor_questions:[] },
      { test_name:"Total Cholesterol", value:175, unit:"mg/dL", reference_range:"< 200", ref_min:null, ref_max:200, flag:"Normal", gauge_pct:73,
        explanation:"Total cholesterol is a combined measure of all fatty substances in your blood. At 175 mg/dL, it is below the recommended limit of 200, which is good for heart health.",
        doctor_questions:[] },
      { test_name:"LDL Cholesterol", value:95, unit:"mg/dL", reference_range:"< 100", ref_min:null, ref_max:100, flag:"Normal", gauge_pct:79,
        explanation:"LDL is called 'bad cholesterol' because high levels can build up in artery walls. Your LDL of 95 mg/dL is just under the optimal limit of 100 — a healthy result.",
        doctor_questions:[] },
      { test_name:"HDL Cholesterol", value:62, unit:"mg/dL", reference_range:"> 50", ref_min:50, ref_max:null, flag:"Normal", gauge_pct:67,
        explanation:"HDL is 'good cholesterol' that helps remove harmful cholesterol from your arteries. At 62 mg/dL your HDL is above the healthy threshold, offering good protection for your heart.",
        doctor_questions:[] },
      { test_name:"TSH (Thyroid Stimulating Hormone)", value:2.1, unit:"mIU/mL", reference_range:"0.4 - 4.0", ref_min:0.4, ref_max:4.0, flag:"Normal", gauge_pct:44,
        explanation:"TSH is the hormone your brain produces to control how active your thyroid gland is. A level of 2.1 mIU/mL sits comfortably in the normal range, indicating your thyroid is functioning well.",
        doctor_questions:[] },
      { test_name:"Serum Creatinine", value:0.8, unit:"mg/dL", reference_range:"0.6 - 1.1", ref_min:0.6, ref_max:1.1, flag:"Normal", gauge_pct:61,
        explanation:"Creatinine is a waste product filtered out by your kidneys, and its level shows how well they are working. Your level of 0.8 mg/dL is normal, suggesting your kidneys are filtering waste effectively.",
        doctor_questions:[] },
    ],
  },

  diabetic: {
    label:   "Diabetic Pattern (Rajesh, 52M)",
    patient: { age: 52, gender: "male" },
    tests: [
      { test_name:"HbA1c (Glycosylated Haemoglobin)", value:8.1, unit:"%", reference_range:"4.0 - 5.6", ref_min:4.0, ref_max:5.6, flag:"See Doctor", gauge_pct:100,
        explanation:"HbA1c reflects your average blood sugar level over the past 2–3 months. Your level of 8.1% is significantly above the normal maximum of 5.6%, indicating that blood sugar has been elevated for a sustained period.",
        doctor_questions:["What HbA1c target should I be aiming for with my current condition?","Should my diabetes medication or insulin dose be adjusted based on this result?"] },
      { test_name:"Fasting Blood Glucose", value:162, unit:"mg/dL", reference_range:"70 - 100", ref_min:70, ref_max:100, flag:"See Doctor", gauge_pct:100,
        explanation:"Fasting blood glucose measures sugar in your blood after not eating overnight. A fasting reading of 162 mg/dL is well above the normal upper limit of 100, indicating elevated blood sugar that needs attention.",
        doctor_questions:["Is this fasting glucose reading dangerous, and how urgently do I need to act?","What dietary or medication changes could bring this level down?"] },
      { test_name:"Total Cholesterol", value:218, unit:"mg/dL", reference_range:"< 200", ref_min:null, ref_max:200, flag:"Caution", gauge_pct:91,
        explanation:"Total cholesterol is the combined measure of all fatty substances circulating in your blood. At 218 mg/dL, it is slightly above the recommended limit of 200, which modestly increases cardiovascular risk.",
        doctor_questions:["Given my blood sugar levels, is this cholesterol level particularly concerning for my heart?","Do I need cholesterol-lowering medication alongside my diabetes management?"] },
      { test_name:"LDL Cholesterol", value:142, unit:"mg/dL", reference_range:"< 100", ref_min:null, ref_max:100, flag:"See Doctor", gauge_pct:100,
        explanation:"LDL is the 'bad cholesterol' that can build up as plaque in artery walls over time. Your LDL of 142 mg/dL is 42% above the optimal limit of 100, raising cardiovascular risk especially alongside elevated blood sugar.",
        doctor_questions:["Should I start cholesterol-lowering medication given this LDL level?","What dietary changes would have the most impact on reducing my LDL?"] },
      { test_name:"HDL Cholesterol", value:38, unit:"mg/dL", reference_range:"> 40", ref_min:40, ref_max:null, flag:"Caution", gauge_pct:88,
        explanation:"HDL is 'good cholesterol' that helps clear harmful cholesterol from your arteries. Your HDL of 38 mg/dL is slightly below the recommended minimum of 40, meaning your natural heart protection is a little lower than ideal.",
        doctor_questions:["What lifestyle changes can help raise my HDL level?","Does low HDL combined with high blood sugar significantly increase my cardiovascular risk?"] },
      { test_name:"Triglycerides", value:285, unit:"mg/dL", reference_range:"< 150", ref_min:null, ref_max:150, flag:"See Doctor", gauge_pct:100,
        explanation:"Triglycerides are fats in your blood that store unused energy from food. A level of 285 mg/dL is nearly double the normal maximum of 150, and very high triglycerides are linked to both diabetes and heart disease risk.",
        doctor_questions:["Is this triglyceride level high enough to need medication, or can diet and exercise bring it down?","How are my high blood sugar and high triglycerides connected?"] },
      { test_name:"Serum Creatinine", value:1.4, unit:"mg/dL", reference_range:"0.7 - 1.3", ref_min:0.7, ref_max:1.3, flag:"Caution", gauge_pct:90,
        explanation:"Creatinine is a waste product your kidneys filter out, and slightly elevated levels can be an early sign of kidney stress. At 1.4 mg/dL, your creatinine is marginally above the normal range — in a person with diabetes this warrants monitoring.",
        doctor_questions:["Could my high blood sugar be affecting my kidney function?","Should I have a urine albumin test to check for early kidney damage?"] },
      { test_name:"Serum Uric Acid", value:7.8, unit:"mg/dL", reference_range:"3.4 - 7.0", ref_min:3.4, ref_max:7.0, flag:"Caution", gauge_pct:93,
        explanation:"Uric acid is a waste product formed when the body breaks down purines found in certain foods. Your level of 7.8 mg/dL is slightly above the normal upper limit of 7.0, which can sometimes raise the risk of gout or kidney stones.",
        doctor_questions:["Could my diet or diabetes medications be contributing to my elevated uric acid?","At what level does uric acid become high enough to require treatment?"] },
      { test_name:"Haemoglobin", value:13.8, unit:"g/dL", reference_range:"13.5 - 17.5", ref_min:13.5, ref_max:17.5, flag:"Normal", gauge_pct:66,
        explanation:"Haemoglobin is the protein in red blood cells that carries oxygen around your body. Your level of 13.8 g/dL is within the normal range, indicating healthy oxygen-carrying capacity.",
        doctor_questions:[] },
      { test_name:"TSH (Thyroid Stimulating Hormone)", value:3.2, unit:"mIU/mL", reference_range:"0.4 - 4.0", ref_min:0.4, ref_max:4.0, flag:"Normal", gauge_pct:67,
        explanation:"TSH is the hormone that signals your thyroid to produce thyroid hormones, which control metabolism. Your level of 3.2 mIU/mL is within the normal range, indicating your thyroid is functioning properly.",
        doctor_questions:[] },
    ],
  },

  lipids: {
    label:   "Lipid Issues (Amit, 45M)",
    patient: { age: 45, gender: "male" },
    tests: [
      { test_name:"Total Cholesterol", value:268, unit:"mg/dL", reference_range:"< 200", ref_min:null, ref_max:200, flag:"See Doctor", gauge_pct:100,
        explanation:"Total cholesterol is the combined measurement of all fatty substances in your blood. At 268 mg/dL — 34% above the limit of 200 — your cholesterol significantly increases your risk of artery disease and heart problems.",
        doctor_questions:["Is medication needed to control my cholesterol at this level?","What specific dietary changes would have the most impact on lowering my total cholesterol?"] },
      { test_name:"LDL Cholesterol", value:188, unit:"mg/dL", reference_range:"< 100", ref_min:null, ref_max:100, flag:"See Doctor", gauge_pct:100,
        explanation:"LDL is the 'bad cholesterol' that accumulates as plaque in your artery walls over time. Your LDL of 188 mg/dL is 88% above the optimal limit, placing you at high risk for cardiovascular disease.",
        doctor_questions:["Given this LDL level, do I need to start statin therapy immediately?","How long would it realistically take to lower my LDL through lifestyle changes alone?"] },
      { test_name:"HDL Cholesterol", value:32, unit:"mg/dL", reference_range:"> 40", ref_min:40, ref_max:null, flag:"See Doctor", gauge_pct:100,
        explanation:"HDL is 'good cholesterol' that transports harmful cholesterol away from your arteries. Your HDL of 32 mg/dL is well below the minimum healthy level of 40, meaning you have reduced natural protection against artery disease.",
        doctor_questions:["What are the most effective ways to raise my HDL level?","Does having both very high LDL and low HDL significantly compound my heart risk?"] },
      { test_name:"Triglycerides", value:320, unit:"mg/dL", reference_range:"< 150", ref_min:null, ref_max:150, flag:"See Doctor", gauge_pct:100,
        explanation:"Triglycerides are fats stored in your blood from excess calories, and very high levels stress both the heart and pancreas. Your level of 320 mg/dL is more than double the normal limit — a significant cardiovascular risk factor.",
        doctor_questions:["Are my triglycerides high enough to risk pancreatitis, or just cardiovascular disease?","Which is more urgent to address — my high triglycerides or high LDL?"] },
      { test_name:"VLDL Cholesterol", value:64, unit:"mg/dL", reference_range:"< 30", ref_min:null, ref_max:30, flag:"See Doctor", gauge_pct:100,
        explanation:"VLDL carries triglycerides in your blood, and high VLDL is directly linked to elevated triglyceride levels. At 64 mg/dL — more than double the upper limit — this reinforces the concern about your overall cardiovascular risk.",
        doctor_questions:["Does a high VLDL mean I have a metabolic problem that needs investigation?","Will treating my triglycerides also bring my VLDL down?"] },
      { test_name:"Fasting Blood Glucose", value:96, unit:"mg/dL", reference_range:"70 - 100", ref_min:70, ref_max:100, flag:"Normal", gauge_pct:80,
        explanation:"Fasting blood glucose measures the sugar level in your blood after not eating overnight. At 96 mg/dL your level is within the healthy range, suggesting your blood sugar control is currently normal.",
        doctor_questions:[] },
      { test_name:"Haemoglobin", value:15.2, unit:"g/dL", reference_range:"13.5 - 17.5", ref_min:13.5, ref_max:17.5, flag:"Normal", gauge_pct:72,
        explanation:"Haemoglobin is the protein in red blood cells that carries oxygen around your body. Your level of 15.2 g/dL is comfortably within the normal range for a man, indicating healthy oxygen-carrying capacity.",
        doctor_questions:[] },
      { test_name:"TSH (Thyroid Stimulating Hormone)", value:1.8, unit:"mIU/mL", reference_range:"0.4 - 4.0", ref_min:0.4, ref_max:4.0, flag:"Normal", gauge_pct:38,
        explanation:"TSH is the pituitary hormone that regulates your thyroid gland's activity. At 1.8 mIU/mL, your TSH is well within the normal range, indicating your thyroid is functioning as it should.",
        doctor_questions:[] },
      { test_name:"Serum ALT / SGPT", value:48, unit:"U/L", reference_range:"< 56", ref_min:null, ref_max:56, flag:"Normal", gauge_pct:71,
        explanation:"ALT is a liver enzyme that rises in the blood when liver cells are damaged or inflamed. Your level of 48 U/L is within the normal range, suggesting your liver is not under significant stress.",
        doctor_questions:[] },
      { test_name:"Serum AST / SGOT", value:42, unit:"U/L", reference_range:"< 40", ref_min:null, ref_max:40, flag:"Caution", gauge_pct:88,
        explanation:"AST is a liver and muscle enzyme, and slightly elevated levels can indicate mild liver stress. Your level of 42 U/L is marginally above the normal upper limit of 40 — worth monitoring especially given your lipid levels.",
        doctor_questions:["Could my high cholesterol and triglycerides be contributing to liver enzyme elevation?","Should I have a more detailed liver function panel done?"] },
    ],
  },

  anemia: {
    label:   "Anaemia + Deficiencies (Sunita, 34F)",
    patient: { age: 34, gender: "female" },
    tests: [
      { test_name:"Haemoglobin", value:8.9, unit:"g/dL", reference_range:"12.0 - 15.5", ref_min:12.0, ref_max:15.5, flag:"See Doctor", gauge_pct:48,
        explanation:"Haemoglobin is the protein in red blood cells that carries oxygen to every organ and tissue in your body. Your level of 8.9 g/dL is well below the normal minimum of 12, meaning your blood is carrying significantly less oxygen than it should.",
        doctor_questions:["What is causing my low haemoglobin — iron deficiency, B12 deficiency, or something else?","Do I need a blood transfusion or iron injections at this level?"] },
      { test_name:"RBC Count", value:3.2, unit:"mill/cumm", reference_range:"3.8 - 5.2", ref_min:3.8, ref_max:5.2, flag:"Caution", gauge_pct:51,
        explanation:"The red blood cell count measures how many red blood cells are present in your blood. Your count of 3.2 mill/cumm is below the normal range, consistent with anaemia and suggesting reduced red cell production.",
        doctor_questions:["Could my low RBC count and low haemoglobin have a common cause?","Are there other tests needed to understand why my red cell count is low?"] },
      { test_name:"MCV (Mean Corpuscular Volume)", value:68, unit:"fL", reference_range:"80 - 100", ref_min:80, ref_max:100, flag:"Caution", gauge_pct:57,
        explanation:"MCV measures the average size of your red blood cells — smaller cells often indicate iron deficiency. Your MCV of 68 fL is below the normal range, which combined with your low haemoglobin strongly suggests iron-deficiency anaemia.",
        doctor_questions:["Does a low MCV confirm I have iron-deficiency anaemia?","How long would it take for iron supplements to bring my MCV back to normal?"] },
      { test_name:"Serum Ferritin", value:6, unit:"ng/mL", reference_range:"10 - 120", ref_min:10, ref_max:120, flag:"See Doctor", gauge_pct:4,
        explanation:"Ferritin is the storage protein for iron in your body, and low levels indicate your iron stores are nearly depleted. Your ferritin of 6 ng/mL is critically low, confirming severe iron deficiency as a likely cause of your anaemia.",
        doctor_questions:["Do I need intravenous iron therapy, or can oral supplements be enough at this ferritin level?","What is causing me to lose iron — should I be investigated for internal bleeding?"] },
      { test_name:"Serum Iron", value:38, unit:"mcg/dL", reference_range:"50 - 170", ref_min:50, ref_max:170, flag:"See Doctor", gauge_pct:19,
        explanation:"Serum iron measures the amount of iron currently circulating in your blood. At 38 mcg/dL, your iron is below the normal range of 50–170, confirming that your body has limited iron available for making red blood cells.",
        doctor_questions:["Should I take iron supplements on an empty stomach or with food for better absorption?","Are there dietary changes that can increase my iron intake alongside supplementation?"] },
      { test_name:"Vitamin B12 (Cyanocobalamin)", value:142, unit:"pg/mL", reference_range:"200 - 900", ref_min:200, ref_max:900, flag:"See Doctor", gauge_pct:13,
        explanation:"Vitamin B12 is essential for producing healthy red blood cells and maintaining your nervous system. Your level of 142 pg/mL is below the normal minimum of 200, indicating a deficiency that can cause anaemia and neurological symptoms if untreated.",
        doctor_questions:["Do I need B12 injections, or can I correct this with oral supplements?","Could my B12 deficiency be due to poor absorption rather than low dietary intake?"] },
      { test_name:"Vitamin D Total (25-OH)", value:11, unit:"ng/mL", reference_range:"30 - 100", ref_min:30, ref_max:100, flag:"See Doctor", gauge_pct:9,
        explanation:"Vitamin D is important for bone health, immune function, and muscle strength. Your level of 11 ng/mL is significantly below the normal minimum of 30, indicating a deficiency that may be causing fatigue and weakening your bones.",
        doctor_questions:["What dose of Vitamin D supplement do I need, and for how long?","Should I have a bone density scan given this level of Vitamin D deficiency?"] },
      { test_name:"Total WBC Count", value:5800, unit:"cells/cumm", reference_range:"4000 - 11000", ref_min:4000, ref_max:11000, flag:"Normal", gauge_pct:44,
        explanation:"White blood cells are your body's immune defence cells that fight infections. Your count of 5800 cells/cumm is well within the normal range, indicating your immune system is functioning properly.",
        doctor_questions:[] },
      { test_name:"Platelet Count", value:3.20, unit:"Lacs/cumm", reference_range:"1.50 - 4.50", ref_min:1.5, ref_max:4.5, flag:"Normal", gauge_pct:59,
        explanation:"Platelets are the tiny blood cells responsible for clotting when you have a cut or injury. Your count of 3.20 Lacs/cumm is comfortably within the normal range, meaning your blood's clotting ability is normal.",
        doctor_questions:[] },
      { test_name:"TSH (Thyroid Stimulating Hormone)", value:2.8, unit:"mIU/mL", reference_range:"0.4 - 4.0", ref_min:0.4, ref_max:4.0, flag:"Normal", gauge_pct:58,
        explanation:"TSH is the hormone that controls how active your thyroid gland is. At 2.8 mIU/mL, your TSH is within the normal range, indicating your thyroid function is not contributing to your fatigue or anaemia.",
        doctor_questions:[] },
    ],
  },
};

// ── Compare presets ───────────────────────────────────────────────────────────

const COMPARE_PRESETS = {
  diabetes_treatment: {
    label: "Diabetes: Before & After Treatment (Rajesh, 52M)",
    summary: { improved: 5, worsened: 0, stable: 0, total_compared: 5 },
    diff: [
      { test_name:"HbA1c (Glycosylated Haemoglobin)", old_value:8.1, new_value:6.5, old_unit:"%", new_unit:"%", old_flag:"See Doctor", new_flag:"Caution", change:"improved" },
      { test_name:"Fasting Blood Glucose", old_value:162, new_value:118, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"See Doctor", new_flag:"Caution", change:"improved" },
      { test_name:"LDL Cholesterol", old_value:142, new_value:108, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"See Doctor", new_flag:"Caution", change:"improved" },
      { test_name:"Triglycerides", old_value:285, new_value:168, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"See Doctor", new_flag:"Caution", change:"improved" },
      { test_name:"Serum Creatinine", old_value:1.4, new_value:1.1, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"Caution", new_flag:"Normal", change:"improved" },
    ],
  },

  lipid_worsening: {
    label: "Lipid Panel: Gradual Worsening (Amit, 45M)",
    summary: { improved: 0, worsened: 5, stable: 0, total_compared: 5 },
    diff: [
      { test_name:"Total Cholesterol", old_value:218, new_value:268, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"Caution", new_flag:"See Doctor", change:"worsened" },
      { test_name:"LDL Cholesterol", old_value:128, new_value:188, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"See Doctor", new_flag:"See Doctor", change:"worsened" },
      { test_name:"HDL Cholesterol", old_value:41, new_value:32, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"Normal", new_flag:"See Doctor", change:"worsened" },
      { test_name:"Triglycerides", old_value:195, new_value:320, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"See Doctor", new_flag:"See Doctor", change:"worsened" },
      { test_name:"Fasting Blood Glucose", old_value:92, new_value:106, old_unit:"mg/dL", new_unit:"mg/dL", old_flag:"Normal", new_flag:"Caution", change:"worsened" },
    ],
  },
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function showSection(id)  { $(id)?.classList.remove("hidden"); }
function hideSection(id)  { $(id)?.classList.add("hidden"); }
function showError(msg)   { const b=$("error-banner"); b.textContent=msg; b.classList.remove("hidden"); }
function hideError()      { $("error-banner").classList.add("hidden"); }
function showLoading(txt,sub="") { $("loading-text").textContent=txt; $("loading-sub").textContent=sub; $("loading-overlay").classList.remove("hidden"); }
function hideLoading()    { $("loading-overlay").classList.add("hidden"); }

// ── Server ping ───────────────────────────────────────────────────────────────
async function pingServer() {
  const dot = $("status-dot");
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (r.ok) {
      dot.classList.add("ok");
      dot.setAttribute("aria-label", "Backend status: online");
    } else {
      dot.classList.add("fail");
      dot.setAttribute("aria-label", "Backend status: error");
    }
  } catch {
    dot.classList.add("fail");
    dot.setAttribute("aria-label", "Backend status: offline");
  }
}

// ── Upload setup ──────────────────────────────────────────────────────────────
function setupUpload() {
  const area  = $("upload-area");
  const input = $("file-input");
  const btn   = $("analyze-btn");

  const handleFile = (file) => {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
      showError("Please select a PDF file."); return;
    }
    S.mainFile     = file;
    S.presetActive = false;
    $("upload-text").textContent     = "PDF selected";
    $("upload-filename").textContent = file.name;
    $("upload-filename").classList.remove("hidden");
    $("demo-pdf-link").style.display = "none";
    btn.disabled = false;
    hideError();
  };

  area.addEventListener("click",  () => input.click());
  area.addEventListener("dragover", e => { e.preventDefault(); area.classList.add("drag-over"); });
  area.addEventListener("dragleave", () => area.classList.remove("drag-over"));
  area.addEventListener("drop", e => { e.preventDefault(); area.classList.remove("drag-over"); handleFile(e.dataTransfer.files[0]); });
  input.addEventListener("change", () => handleFile(input.files[0]));

  // FIX: keyboard handler — Enter/Space now trigger upload (was mouse-only before)
  area.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });

  btn.addEventListener("click", analyzeReport);
}

// ── Toggle setup (language / view mode) ──────────────────────────────────────

// FIX: debounce to prevent race condition when user clicks lang then mode quickly
let _reExplainTimer = null;
function scheduleReExplain() {
  clearTimeout(_reExplainTimer);
  _reExplainTimer = setTimeout(reExplain, 300);
}

function setupToggles() {
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".lang-btn").forEach(b => {
        b.classList.remove("active");
        // FIX: keep aria-pressed in sync
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
      S.lang = btn.dataset.lang;
      if (S.tests.length > 0) scheduleReExplain();
    });
  });

  document.querySelectorAll(".view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".view-btn").forEach(b => {
        b.classList.remove("active");
        // FIX: keep aria-pressed in sync
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
      S.mode = btn.dataset.mode;
      if (S.tests.length > 0) scheduleReExplain();
    });
  });
}

// ── Analyze ───────────────────────────────────────────────────────────────────
async function analyzeReport() {
  hideError();

  if (!S.mainFile) {
    showError(S.presetActive
      ? "A preset is loaded. Upload a PDF to run a fresh analysis."
      : "Please select a PDF file first.");
    return;
  }

  showLoading("Extracting test results…", "This may take 20–30 seconds");

  const fd = new FormData();
  fd.append("file", S.mainFile);
  fd.append("language", S.lang);
  fd.append("mode", S.mode);

  try {
    const r = await fetch(`${API_BASE}/analyze`, { method:"POST", body:fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${r.status}`);
    }
    const data = await r.json();
    S.tests        = data.tests;
    S.patient      = data.patient;
    S.presetActive = false;
    S.flaggedTests = data.tests.map(({ explanation, doctor_questions, ...rest }) => rest);
    S.chat.ctx     = buildChatContext(data.tests);
    S.chat.turns   = 0;
    S.chat.history = [];

    renderSummary(data);
    renderResults(data.tests);
    showSection("toggle-row");
    showSection("results-section");
    showSection("chat-section");
    showSection("export-section");
    updateChatTurnsNote();
  } catch(e) {
    showError(e.message || "Analysis failed. Please try again.");
  } finally {
    hideLoading();
  }
}

// ── Re-explain (language / mode change) ──────────────────────────────────────
async function reExplain() {
  if (!S.flaggedTests.length) return;

  showLoading("Re-generating explanations…", `Switching to ${S.lang} · ${S.mode} view`);

  const fd = new FormData();
  fd.append("tests",    JSON.stringify(S.flaggedTests));
  fd.append("age",      S.patient.age);
  fd.append("gender",   S.patient.gender);
  fd.append("language", S.lang);
  fd.append("mode",     S.mode);

  try {
    const r = await fetch(`${API_BASE}/explain`, { method:"POST", body:fd });
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const data = await r.json();
    S.tests = data.tests;
    renderResults(data.tests);
  } catch(e) {
    showError("Could not refresh explanations. " + (e.message || ""));
  } finally {
    hideLoading();
  }
}

// ── Render helpers ────────────────────────────────────────────────────────────
function renderSummary(data) {
  const tests    = data.tests || [];
  const normal   = tests.filter(t => t.flag === "Normal").length;
  const caution  = tests.filter(t => t.flag === "Caution").length;
  const danger   = tests.filter(t => t.flag === "See Doctor").length;

  $("stat-total").textContent   = tests.length;
  $("stat-normal").textContent  = normal;
  $("stat-caution").textContent = caution;
  $("stat-danger").textContent  = danger;
  showSection("results-summary");
}

function flagToClass(flag) {
  return { "Normal":"normal", "Caution":"caution", "See Doctor":"see-doctor" }[flag] || "normal";
}

function flagToBadgeClass(flag) {
  return { "Normal":"badge-normal", "Caution":"badge-caution", "See Doctor":"badge-see-doctor" }[flag] || "badge-normal";
}

function renderResults(tests) {
  const container = $("test-cards");
  container.innerHTML = "";

  const allQs = [];
  tests.forEach(t => {
    container.insertAdjacentHTML("beforeend", buildCard(t));
    (t.doctor_questions || []).forEach(q => {
      if (q) allQs.push({ name: t.test_name, q });
    });
  });

  const qCard = $("doctor-questions-card");
  const qList = $("doctor-q-list");
  if (allQs.length) {
    qList.innerHTML = allQs.map(({ name, q }) =>
      `<li><span class="q-test-name">[${esc(name)}]</span> ${esc(q)}</li>`
    ).join("");
    qCard.classList.remove("hidden");
  } else {
    qCard.classList.add("hidden");
  }
}

function buildCard(t) {
  const cls     = flagToClass(t.flag);
  const badgeCls = flagToBadgeClass(t.flag);
  const badgeTxt = { Normal:"✓ Normal", Caution:"⚠ Caution", "See Doctor":"⚑ See Doctor" }[t.flag] || t.flag;
  const ref = t.reference_range || (t.ref_min != null || t.ref_max != null
    ? `${t.ref_min ?? ""}–${t.ref_max ?? ""}` : "");

  // FIX: clamp gauge_pct to 0-100 (backend occasionally returns >100 on extreme values)
  const pct = Math.min(100, Math.max(0, t.gauge_pct ?? 0));

  const qs = (t.doctor_questions || []).filter(Boolean);
  const qHtml = qs.length
    ? `<div class="doctor-q-inline"><ul role="list">${qs.map(q=>`<li>${esc(q)}</li>`).join("")}</ul></div>`
    : "";

  return `
  <div class="test-card ${cls}" role="article" aria-label="${esc(t.test_name)} — ${esc(t.flag)}">
    <div class="test-card-header">
      <span class="test-name">${esc(t.test_name)}</span>
      <span class="test-badge ${badgeCls}">${badgeTxt}</span>
    </div>
    <div class="test-value-row">
      <span class="test-value">${t.value ?? "—"}</span>
      <span class="test-unit">${esc(t.unit || "")}</span>
      ${ref ? `<span class="test-range">Ref: ${esc(ref)}</span>` : ""}
    </div>
    <div class="gauge-track" role="img" aria-label="Value gauge: ${pct}% of normal upper range">
      <div class="gauge-fill" style="width:${pct}%"></div>
    </div>
    ${t.explanation ? `<div class="test-explanation">${esc(t.explanation)}</div>` : ""}
    ${qHtml}
  </div>`;
}

// ── Chat ──────────────────────────────────────────────────────────────────────
function buildChatContext(tests) {
  return JSON.stringify(tests.map(t => ({
    test_name: t.test_name,
    value:     t.value,
    unit:      t.unit,
    flag:      t.flag,
    reference_range: t.reference_range,
  })));
}

function updateChatTurnsNote() {
  const remaining = Math.max(0, CHAT_TURN_LIMIT - S.chat.turns);
  $("chat-turns-note").textContent = `${remaining} question${remaining === 1 ? "" : "s"} remaining in this session`;
}

function setupChat() {
  const input  = $("chat-input");
  const sendBtn = $("send-btn");

  const send = async () => {
    const msg = input.value.trim();
    if (!msg || S.chat.turns >= CHAT_TURN_LIMIT) return;

    appendBubble(msg, "user");
    input.value = "";

    const loadingEl = appendBubble("…", "loading");

    const fd = new FormData();
    fd.append("message",        msg);
    fd.append("report_context", S.chat.ctx);
    fd.append("history",        JSON.stringify(S.chat.history));
    fd.append("age",            S.patient.age);
    fd.append("gender",         S.patient.gender);
    fd.append("language",       S.lang);

    try {
      const r = await fetch(`${API_BASE}/chat`, { method:"POST", body:fd });
      if (!r.ok) throw new Error(`Server error ${r.status}`);
      const data = await r.json();

      loadingEl.remove();
      appendBubble(data.reply, "ai");

      // FIX: increment turns on success only — previously incremented before the call
      S.chat.turns++;
      S.chat.history.push({ role:"user", content:msg });
      S.chat.history.push({ role:"assistant", content:data.reply });
      updateChatTurnsNote();

      if (S.chat.turns >= CHAT_TURN_LIMIT) {
        sendBtn.disabled = true;
        input.disabled   = true;
        appendBubble("You've used all questions for this session. Reload the page to start a new session.", "ai");
      }
    } catch(e) {
      loadingEl.remove();
      appendBubble("Sorry, something went wrong. Please try again.", "ai");
      // FIX: do NOT increment S.chat.turns on failure
    }
  };

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
}

function appendBubble(text, type) {
  const box = $("chat-messages");
  const el  = document.createElement("div");
  el.className = `bubble bubble-${type}`;
  el.textContent = text;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

// ── Compare ───────────────────────────────────────────────────────────────────
function setupCompare() {
  const setupCompareUpload = (areaId, inputId, slotKey, labelBase) => {
    const area  = $(areaId);
    const input = $(inputId);

    const handleFile = (file) => {
      if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
        showError("Please select a PDF file."); return;
      }
      S[slotKey] = file;
      area.textContent = file.name;
      area.classList.add("loaded");
      // FIX: update aria-label with filename so screen readers retain context
      area.setAttribute("aria-label", `${labelBase}: ${file.name}`);
      if (S.compareFile1 && S.compareFile2) $("compare-btn").disabled = false;
    };

    area.addEventListener("click", () => input.click());
    input.addEventListener("change", () => handleFile(input.files[0]));

    // FIX: keyboard handler for compare upload boxes
    area.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });
  };

  setupCompareUpload("compare-area1", "compare-file1", "compareFile1", "Older report");
  setupCompareUpload("compare-area2", "compare-file2", "compareFile2", "Newer report");

  $("compare-btn").addEventListener("click", compareReports);
}

async function compareReports() {
  // FIX: clear stale errors from previous compare operations
  hideError();

  if (!S.compareFile1 || !S.compareFile2) {
    showError("Please upload both reports before comparing."); return;
  }

  showLoading("Comparing reports…", "Extracting and analysing both PDFs");

  const fd = new FormData();
  fd.append("file1", S.compareFile1);
  fd.append("file2", S.compareFile2);

  try {
    const r = await fetch(`${API_BASE}/compare`, { method:"POST", body:fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${r.status}`);
    }
    const data = await r.json();
    renderComparison(data);
  } catch(e) {
    showError(e.message || "Comparison failed. Please try again.");
  } finally {
    hideLoading();
  }
}

function renderComparison({ diff, summary }) {
  $("cmp-improved").textContent = summary.improved;
  $("cmp-worsened").textContent = summary.worsened;
  $("cmp-stable").textContent   = summary.stable;

  const tbody = $("compare-tbody");
  tbody.innerHTML = diff.map(d => `
    <tr>
      <td>${esc(d.test_name)}</td>
      <td>${d.old_value != null ? `${d.old_value} ${esc(d.old_unit||"")}` : "—"}</td>
      <td>${d.new_value != null ? `${d.new_value} ${esc(d.new_unit||"")}` : "—"}</td>
      <td>${d.old_flag ? `<span class="test-badge ${flagToBadgeClass(d.old_flag)}">${esc(d.old_flag)}</span>` : "—"}</td>
      <td>${d.new_flag ? `<span class="test-badge ${flagToBadgeClass(d.new_flag)}">${esc(d.new_flag)}</span>` : "—"}</td>
      <td>${buildChip(d.change)}</td>
    </tr>`).join("");

  showSection("compare-results");
}

function buildChip(change) {
  const map = {
    improved: ["chip-improved","↑ Improved"],
    worsened: ["chip-worsened","↓ Worsened"],
    stable:   ["chip-stable",  "→ Stable"],
    new:      ["chip-new",     "+ New"],
    missing:  ["chip-missing", "− Missing"],
  };
  const [cls, label] = map[change] || ["chip-stable", change];
  return `<span class="chip ${cls}">${label}</span>`;
}

// ── Export ────────────────────────────────────────────────────────────────────
function setupExport() {
  $("export-btn").addEventListener("click", exportPDF);
}

async function exportPDF() {
  // FIX: clear stale error from previous operations
  hideError();

  if (!S.tests.length) return;
  showLoading("Generating PDF…");

  const fd = new FormData();
  fd.append("tests",  JSON.stringify(S.tests));
  fd.append("age",    S.patient.age);
  fd.append("gender", S.patient.gender);

  try {
    const r = await fetch(`${API_BASE}/export`, { method:"POST", body:fd });
    if (!r.ok) throw new Error(`PDF generation failed (${r.status})`);
    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = "lab-report-summary.pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) {
    showError(e.message || "PDF export failed. Please try again.");
  } finally {
    hideLoading();
  }
}

// ── Demo presets ──────────────────────────────────────────────────────────────
function setupDemoPresets() {
  // Single-report presets
  const sel     = $("demo-select");
  const loadBtn = $("demo-load-btn");
  const pdfLink = $("demo-pdf-link");

  sel.addEventListener("change", () => {
    loadBtn.disabled = !sel.value;
    if (sel.value) {
      pdfLink.href         = `${API_BASE}/static/sample_${sel.value}.pdf`;
      pdfLink.style.display = "";
    } else {
      pdfLink.style.display = "none";
    }
  });

  loadBtn.addEventListener("click", () => {
    if (sel.value) loadPreset(sel.value);
  });

  // Compare presets
  const cmpSel = $("compare-demo-select");
  const cmpBtn = $("compare-demo-btn");

  cmpSel.addEventListener("change", () => {
    cmpBtn.disabled = !cmpSel.value;
  });

  cmpBtn.addEventListener("click", () => {
    if (cmpSel.value) loadComparePreset(cmpSel.value);
  });
}

function loadPreset(key) {
  const preset = SAMPLE_PRESETS[key];
  if (!preset) return;

  hideError();

  S.tests        = preset.tests;
  S.patient      = preset.patient;
  S.presetActive = true;
  S.mainFile     = null;
  S.flaggedTests = preset.tests.map(({ explanation, doctor_questions, ...rest }) => rest);
  S.chat.ctx     = buildChatContext(preset.tests);
  S.chat.turns   = 0;
  S.chat.history = [];

  // Update upload area to show preset name
  $("upload-text").textContent     = preset.label;
  $("upload-filename").textContent = "Preset loaded — upload a PDF to run a real analysis";
  $("upload-filename").classList.remove("hidden");
  $("analyze-btn").disabled = true;

  renderSummary({ tests: preset.tests });
  renderResults(preset.tests);
  showSection("toggle-row");
  showSection("results-section");
  showSection("chat-section");
  showSection("export-section");
  updateChatTurnsNote();

  // Scroll to results
  $("results-section")?.scrollIntoView({ behavior:"smooth", block:"start" });
}

function loadComparePreset(key) {
  const preset = COMPARE_PRESETS[key];
  if (!preset) return;

  hideError();

  // Reset compare upload boxes to show preset name
  const area1 = $("compare-area1");
  const area2 = $("compare-area2");
  area1.textContent = `${preset.label.split(":")[0]} — Before`;
  area2.textContent = `${preset.label.split(":")[0]} — After`;
  area1.classList.add("loaded");
  area2.classList.add("loaded");

  renderComparison(preset);
  $("compare-results")?.scrollIntoView({ behavior:"smooth", block:"start" });
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupUpload();
  setupToggles();
  setupChat();
  setupCompare();
  setupExport();
  setupDemoPresets();
  pingServer();
});
