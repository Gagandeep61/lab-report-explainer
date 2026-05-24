# rules.py — deterministic rules engine
# This module contains ZERO LLM calls. All decisions here are pure Python logic.
#
# WHY: LLMs hallucinate arithmetic. If glucose is 105 and normal max is 100,
# an LLM might say it's "slightly high" or it might say it's "perfectly fine."
# A deterministic comparison never makes that mistake.
# This is the architectural separation that makes the app trustworthy.
 
import re
from typing import Optional
from units import normalize_unit_alias as normalize_unit 
 
def parse_reference_range(range_str: str | None) -> tuple[float | None, float | None]:
    """
    Parse a reference range string from the lab report into (min, max).
    
    Handles common Indian lab report formats:
      "70 - 100"         → (70.0, 100.0)
      "70-100"           → (70.0, 100.0)
      "< 200"            → (None, 200.0)
      "<200"             → (None, 200.0)
      "> 40"             → (40.0, None)
      "Upto 5.6"         → (None, 5.6)
      "Up to 200"        → (None, 200.0)
      "4.0 to 5.6"       → (4.0, 5.6)
      "4.0–5.6"          → (4.0, 5.6)  ← em-dash from OCR
      "60 - 170 μg/dL"   → (60.0, 170.0)  ← with unit suffix
    """
    if not range_str or range_str.strip() in ("", "N/A", "-", "—", "null", "None"):
        return None, None
 
    s = range_str.strip()
 
    # Remove unit suffixes (mg/dL, mmol/L, etc.) to isolate numbers
    s = re.sub(r'[a-zA-Zμµ%°/²³]+.*$', '', s).strip()
 
    # Handle "< X" or "<X" or "Upto X" or "Up to X" → (None, X)
    m = re.match(r'^[<≤]?\s*(upto|up to|less than|below)?\s*([<≤])?\s*([\d.]+)', s, re.IGNORECASE)
    if s.startswith('<') or re.match(r'^(upto|up to)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return None, float(nums[0])
 
    # Handle "> X" or ">=X" → (X, None)
    if s.startswith('>') or re.match(r'^(above|greater than)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return float(nums[0]), None
 
    # Handle "X - Y", "X to Y", "X – Y" (em-dash), "X–Y"
    parts = re.split(r'\s*[-–—to]+\s*', s, maxsplit=1)
    if len(parts) == 2:
        try:
            lo = float(re.findall(r'[\d.]+', parts[0])[0])
            hi = float(re.findall(r'[\d.]+', parts[1])[0])
            return lo, hi
        except (IndexError, ValueError):
            pass
 
    # Single number fallback — treat as upper limit
    nums = re.findall(r'[\d.]+', s)
    if len(nums) == 1:
        return None, float(nums[0])
 
    return None, None
 
 
def compute_gauge_pct(value: float, ref_min: float | None, ref_max: float | None) -> int:
    """
    Compute gauge fill percentage for the visual bar.
    
    Logic from design brief: Width = (value / max_of_range * 1.2) * 100%, capped at 100%.
    For lower-bound-only tests (e.g. HDL where higher is better), we invert:
      gauge shows danger level, so low HDL = high fill = red.
    """
    if ref_max is not None and ref_max > 0:
        # Normal case: value vs upper bound
        pct = (value / ref_max) * (100 / 1.2)
        return min(100, max(3, round(pct)))
 
    if ref_min is not None and ref_min > 0:
        # Lower-bound-only test (e.g. HDL): invert
        # Low value = dangerous = high gauge fill
        pct = (ref_min / value) * (100 / 1.2) if value > 0 else 100
        return min(100, max(3, round(pct)))
 
    return 50  # Can't compute — show midpoint
 
 
def determine_flag(
    value: float,
    ref_min: float | None,
    ref_max: float | None,
    caution_band: tuple[float, float] | None = None,
) -> str:
    """
    Return flag: "Normal", "Caution", or "See Doctor".
    
    Thresholds:
      - Within range: Normal
      - Outside range by ≤20%: Caution
      - Outside range by >20%: See Doctor
    
    Special caution_band: for tests like HbA1c where a specific
    intermediate range exists (5.6-6.4 = pre-diabetic).
    """
    # Both bounds present
    if ref_min is not None and ref_max is not None:
        if ref_min <= value <= ref_max:
            return "Normal"
        
        # Check caution band first (e.g. HbA1c pre-diabetic)
        if caution_band and caution_band[0] <= value <= caution_band[1]:
            return "Caution"
        
        # Calculate % deviation from the breached boundary
        if value < ref_min:
            deviation = (ref_min - value) / ref_min
        else:
            deviation = (value - ref_max) / ref_max
        
        return "Caution" if deviation <= 0.20 else "See Doctor"
 
    # Upper bound only (lower is always fine or not specified)
    if ref_max is not None:
        if value <= ref_max:
            return "Normal"
        deviation = (value - ref_max) / ref_max
        return "Caution" if deviation <= 0.20 else "See Doctor"
 
    # Lower bound only (higher-is-better tests like HDL, eGFR)
    if ref_min is not None:
        if value >= ref_min:
            return "Normal"
        deviation = (ref_min - value) / ref_min
        return "Caution" if deviation <= 0.20 else "See Doctor"
 
    # No range at all — can't determine
    return "Normal"
 
 
def apply_rules(test: dict, age: int, gender: str) -> dict:
    """
    Process a single extracted test dict through the full rules pipeline:
    1. Normalize units
    2. Parse reference range (from report, then fallback)
    3. Apply flag logic
    4. Compute gauge percentage
    
    Input test dict (from extractor):
      { test_name, value, unit, reference_range }
    
    Returns enriched dict with: flag, ref_min, ref_max, gauge_pct, unit (normalized)
    """
    result = dict(test)  # Don't mutate input
 
    # Step 1: Normalize units
    norm_value = test.get("value")
    norm_unit = normalize_unit(test.get("unit"))
    
    result["value"] = norm_value
    result["unit"] = norm_unit
 
    # Step 2: Parse reference range
    # Priority: report's own printed range > fallback dict
    ref_min, ref_max = parse_reference_range(test.get("reference_range"))
 
    if ref_min is None and ref_max is None:
        # No range in report and no fallback — flag logic will skip
        pass
 
    result["ref_min"] = ref_min
    result["ref_max"] = ref_max
 
    # Step 3: Flag — requires a value to work
    if norm_value is None:
        result["flag"] = "Normal"  # Can't flag without a value
        result["gauge_pct"] = 0
        return result
 
    # Check for HbA1c caution band specifically
    caution_band = None
    test_lower = test.get("test_name", "").lower()
    if "hba1c" in test_lower or "a1c" in test_lower:
        caution_band = (5.6, 6.4)
 
    result["flag"] = determine_flag(norm_value, ref_min, ref_max, caution_band)
 
    # Step 4: Gauge percentage
    result["gauge_pct"] = compute_gauge_pct(norm_value, ref_min, ref_max)
 
    return result
 
 
def compare_two_reports(tests_old: list[dict], tests_new: list[dict]) -> list[dict]:
    """
    Compare two sets of flagged test results.
    Returns a diff list with: test_name, old_value, new_value, old_flag,
    new_flag, change ("improved" | "worsened" | "stable" | "new" | "missing").
    
    Two values improve if the flag moved toward Normal (See Doctor → Caution → Normal).
    Two values worsen if the flag moved away from Normal.
    """
    FLAG_RANK = {"Normal": 0, "Caution": 1, "See Doctor": 2}
 
    # Build lookup by test name (lowercase, stripped)
    old_map = {t["test_name"].strip().lower(): t for t in tests_old if t.get("test_name")}
    new_map = {t["test_name"].strip().lower(): t for t in tests_new if t.get("test_name")}
 
    all_keys = set(old_map) | set(new_map)
    diff = []
 
    for key in sorted(all_keys):
        old = old_map.get(key)
        new = new_map.get(key)
 
        if old and not new:
            diff.append({
                "test_name": old["test_name"],
                "old_value": old.get("value"),
                "new_value": None,
                "old_flag": old.get("flag", "Normal"),
                "new_flag": None,
                "old_unit": old.get("unit"),
                "new_unit": None,
                "change": "missing",
            })
        elif new and not old:
            diff.append({
                "test_name": new["test_name"],
                "old_value": None,
                "new_value": new.get("value"),
                "old_flag": None,
                "new_flag": new.get("flag", "Normal"),
                "old_unit": None,
                "new_unit": new.get("unit"),
                "change": "new",
            })
        else:
            old_rank = FLAG_RANK.get(old.get("flag", "Normal"), 0)
            new_rank = FLAG_RANK.get(new.get("flag", "Normal"), 0)
 
            if new_rank < old_rank:
                change = "improved"
            elif new_rank > old_rank:
                change = "worsened"
            else:
                # Same flag — check value delta (>5% = changed)
                ov = old.get("value") or 0
                nv = new.get("value") or 0
                delta = abs(nv - ov) / max(abs(ov), 1)
                change = "stable" if delta < 0.05 else (
                    "improved" if nv < ov and old_rank > 0 else
                    "worsened" if nv > ov and new_rank > 0 else "stable"
                )
 
            diff.append({
                "test_name": new["test_name"],
                "old_value": old.get("value"),
                "new_value": new.get("value"),
                "old_flag": old.get("flag"),
                "new_flag": new.get("flag"),
                "old_unit": old.get("unit"),
                "new_unit": new.get("unit"),
                "change": change,
            })
 
    return diff
 