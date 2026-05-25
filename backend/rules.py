# rules.py — deterministic rules engine
# ZERO LLM calls. All decisions are pure Python logic.
#
# WHY: LLMs hallucinate arithmetic. If glucose is 105 and normal max is 100,
# an LLM might say it's fine. A deterministic comparison never makes that mistake.
# This architectural separation is what makes the app trustworthy.

import re
from units import normalize_unit_alias as normalize_unit
from ranges_fallback import get_fallback_range


def parse_reference_range(range_str: str | None) -> tuple[float | None, float | None]:
    """
    Parse a reference range string from the lab report into (min, max).

    Handles all common Indian lab report formats including edge cases:

    Standard:
      "70 - 100"         → (70.0, 100.0)
      "70-100"           → (70.0, 100.0)
      "< 200"            → (None, 200.0)
      "> 40"             → (40.0, None)

    Comma-formatted (SRL, Thyrocare use these for large numbers):
      "4,000 - 10,000"   → (4000.0, 10000.0)   ← BUG FIX: was parsing as 4-10
      "1,50,000 - 4,00,000" → (150000.0, 400000.0)  ← Indian lakh format too

    Descriptive multi-zone (some labs print zone labels inline):
      "Normal: 4.0 - 5.6 Prediabetes: 5.7 - 6.4"  → (4.0, 5.6)  ← BUG FIX: was returning None
      "Optimal: < 100 Near Optimal: 100 - 129"      → (None, 100.0)
      "Low Risk: >= 60 Moderate Risk: 40 - 59"       → (60.0, None)

    With unit suffix:
      "60 - 170 μg/dL"   → (60.0, 170.0)

    Em-dash from OCR:
      "4.0–5.6"          → (4.0, 5.6)
    """
    if not range_str or range_str.strip() in ("", "N/A", "-", "—", "null", "None"):
        return None, None

    s = range_str.strip()

    # ── FIX 1: Strip thousand/lakh separators from numbers ────────────────────
    # "4,000"    → "4000"
    # "1,50,000" → "150000"  (Indian lakh format)
    # Uses lookahead/lookbehind so only commas BETWEEN digits are removed.
    s = re.sub(r'(?<=\d),(?=\d)', '', s)

    # ── FIX 2: Strip descriptive zone labels before anything else ─────────────
    # "Normal: 4.0 - 5.6 Prediabetes: 5.7 - 6.4" → "4.0 - 5.6  5.7 - 6.4"
    # "Optimal: < 100 Near Optimal: 100 - 129"    → " < 100  100 - 129"
    # Pattern: one+ letters, optional spaces, then colon — replace with space
    s = re.sub(r'[A-Za-z][A-Za-z\s]*:\s*', ' ', s).strip()

    # ── Strip trailing unit suffixes (mg/dL, mmol/L, etc.) ───────────────────
    # Now safe to do this AFTER label stripping above, because labels are gone.
    s = re.sub(r'[a-zA-Zμµ%°/²³]+.*$', '', s).strip()

    if not s:
        return None, None

    # ── Handle upper-bound-only: "< X" or "Upto X" ───────────────────────────
    if s.startswith('<') or re.match(r'^(upto|up to|less than|below)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return None, float(nums[0])

    # ── Handle lower-bound-only: "> X" or "above X" ──────────────────────────
    if s.startswith('>') or re.match(r'^(above|greater than|>=)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return float(nums[0]), None

    # ── Handle range: "X - Y", "X to Y", "X–Y" ───────────────────────────────
    # maxsplit=1 means we only split on the FIRST separator.
    # After label stripping, "4.0 - 5.6  5.7 - 6.4" splits into
    # ["4.0 ", " 5.6  5.7  6.4"] and we take [0] of each → (4.0, 5.6). Correct.
    parts = re.split(r'\s*[-–—]|\s+to\s+', s, maxsplit=1)
    if len(parts) == 2:
        try:
            nums0 = re.findall(r'[\d.]+', parts[0])
            nums1 = re.findall(r'[\d.]+', parts[1])
            if nums0 and nums1:
                lo = float(nums0[0])
                hi = float(nums1[0])
                # Sanity: lo should be less than hi
                if lo < hi:
                    return lo, hi
        except (IndexError, ValueError):
            pass

    # ── Single number fallback → treat as upper limit ─────────────────────────
    nums = re.findall(r'[\d.]+', s)
    if len(nums) == 1:
        return None, float(nums[0])

    return None, None


def compute_gauge_pct(value: float, ref_min: float | None, ref_max: float | None) -> int:
    """
    Compute gauge fill percentage (0-100) for the visual bar.

    Formula from design brief: (value / max_of_range * 1.2) * 100, capped at 100.
    For lower-bound-only tests (HDL, eGFR — higher is better), invert:
    low value = more danger = higher fill.
    """
    if ref_max is not None and ref_max > 0:
        pct = (value / ref_max) * (100 / 1.2)
        return min(100, max(3, round(pct)))

    if ref_min is not None and ref_min > 0:
        pct = (ref_min / value) * (100 / 1.2) if value > 0 else 100
        return min(100, max(3, round(pct)))

    return 50  # Unknown range — show midpoint


def determine_flag(
    value: float,
    ref_min: float | None,
    ref_max: float | None,
    caution_band: tuple[float, float] | None = None,
) -> str:
    """
    Return "Normal", "Caution", or "See Doctor".

    Deviation thresholds:
      Within range          → Normal
      ≤20% outside range    → Caution
      >20% outside range    → See Doctor

    caution_band: optional intermediate zone (e.g. HbA1c 5.6–6.4 = pre-diabetic).
    """
    if ref_min is not None and ref_max is not None:
        if ref_min <= value <= ref_max:
            return "Normal"
        if caution_band and caution_band[0] <= value <= caution_band[1]:
            return "Caution"
        deviation = (
            (ref_min - value) / ref_min if value < ref_min
            else (value - ref_max) / ref_max
        )
        return "Caution" if deviation <= 0.20 else "See Doctor"

    if ref_max is not None:
        if value <= ref_max:
            return "Normal"
        deviation = (value - ref_max) / ref_max
        return "Caution" if deviation <= 0.20 else "See Doctor"

    if ref_min is not None:
        if value >= ref_min:
            return "Normal"
        deviation = (ref_min - value) / ref_min
        return "Caution" if deviation <= 0.20 else "See Doctor"

    # No range at all — cannot determine
    return "Normal"


def apply_rules(test: dict, age: int, gender: str) -> dict:
    """
    Run the full rules pipeline on a single extracted test dict.
    Steps:
      1. Normalize unit alias  (gm% → g/dL etc.)
      2. Parse reference range (report's own range first, fallback dict second)
      3. Determine flag        (Normal / Caution / See Doctor)
      4. Compute gauge %       (for the visual bar)
    """
    result = dict(test)

    # Step 1: Normalize unit alias
    result["unit"] = normalize_unit(test.get("unit"))

    # Step 2: Parse reference range — report's own range takes priority
    ref_min, ref_max = parse_reference_range(test.get("reference_range"))

    if ref_min is None and ref_max is None:
        # Report didn't include a range — try the fallback dict
        fallback = get_fallback_range(test.get("test_name", ""), gender)
        if fallback:
            ref_min, ref_max = fallback

    result["ref_min"] = ref_min
    result["ref_max"] = ref_max

    value = test.get("value")

    if value is None:
        result["flag"]      = "Normal"
        result["gauge_pct"] = 0
        return result

    # Special caution band for HbA1c (pre-diabetic range 5.6–6.4)
    caution_band = None
    if any(x in test.get("test_name", "").lower() for x in ("hba1c", "a1c", "glycosylated")):
        caution_band = (5.6, 6.4)

    # Step 3 + 4
    result["flag"]      = determine_flag(value, ref_min, ref_max, caution_band)
    result["gauge_pct"] = compute_gauge_pct(value, ref_min, ref_max)

    return result


def compare_two_reports(tests_old: list[dict], tests_new: list[dict]) -> list[dict]:
    """
    Diff two sets of flagged tests.
    Change values: "improved" | "worsened" | "stable" | "new" | "missing"
    Improvement = flag moved toward Normal. Worsening = away from Normal.
    """
    FLAG_RANK = {"Normal": 0, "Caution": 1, "See Doctor": 2}

    old_map = {t["test_name"].strip().lower(): t for t in tests_old if t.get("test_name")}
    new_map = {t["test_name"].strip().lower(): t for t in tests_new if t.get("test_name")}

    diff = []
    for key in sorted(set(old_map) | set(new_map)):
        old = old_map.get(key)
        new = new_map.get(key)

        if old and not new:
            diff.append({**old, "old_value": old.get("value"), "new_value": None,
                         "old_flag": old.get("flag"), "new_flag": None,
                         "old_unit": old.get("unit"), "new_unit": None, "change": "missing"})
        elif new and not old:
            diff.append({**new, "old_value": None, "new_value": new.get("value"),
                         "old_flag": None, "new_flag": new.get("flag"),
                         "old_unit": None, "new_unit": new.get("unit"), "change": "new"})
        else:
            old_rank = FLAG_RANK.get(old.get("flag", "Normal"), 0)
            new_rank = FLAG_RANK.get(new.get("flag", "Normal"), 0)
            if new_rank < old_rank:
                change = "improved"
            elif new_rank > old_rank:
                change = "worsened"
            else:
                ov, nv = (old.get("value") or 0), (new.get("value") or 0)
                delta  = abs(nv - ov) / max(abs(ov), 1)
                change = "stable" if delta < 0.05 else (
                    "improved" if nv < ov and old_rank > 0 else
                    "worsened" if nv > ov and new_rank > 0 else "stable"
                )
            diff.append({
                "test_name": new["test_name"],
                "old_value": old.get("value"), "new_value": new.get("value"),
                "old_flag":  old.get("flag"),  "new_flag":  new.get("flag"),
                "old_unit":  old.get("unit"),  "new_unit":  new.get("unit"),
                "change":    change,
            })

    return diff
