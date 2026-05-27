# rules.py — deterministic rules engine
# ZERO LLM calls. All decisions are pure Python logic.

import re
from units import normalize_unit_alias as normalize_unit
from ranges_fallback import get_fallback_range


def parse_reference_range(range_str: str | None) -> tuple[float | None, float | None]:
    if not range_str or range_str.strip() in ("", "N/A", "-", "—", "null", "None"):
        return None, None

    s = range_str.strip()
    s = re.sub(r'(?<=\d),(?=\d)', '', s)
    s = re.sub(r'[A-Za-z][A-Za-z\s]*:\s*', ' ', s).strip()
    s = re.sub(r'[a-zA-Zμµ%°/²³]+.*$', '', s).strip()

    if not s:
        return None, None

    if s.startswith('<') or re.match(r'^(upto|up to|less than|below)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return None, float(nums[0])

    if s.startswith('>') or re.match(r'^(above|greater than|>=)', s, re.IGNORECASE):
        nums = re.findall(r'[\d.]+', s)
        if nums:
            return float(nums[0]), None

    parts = re.split(r'\s*[-–—]|\s+to\s+', s, maxsplit=1)
    if len(parts) == 2:
        try:
            nums0 = re.findall(r'[\d.]+', parts[0])
            nums1 = re.findall(r'[\d.]+', parts[1])
            if nums0 and nums1:
                lo = float(nums0[0])
                hi = float(nums1[0])
                if lo < hi:
                    return lo, hi
        except (IndexError, ValueError):
            pass

    nums = re.findall(r'[\d.]+', s)
    if len(nums) == 1:
        return None, float(nums[0])

    return None, None


def compute_gauge_pct(value: float, ref_min: float | None, ref_max: float | None) -> int:
    if ref_max is not None and ref_max > 0:
        pct = (value / ref_max) * (100 / 1.2)
        return min(100, max(3, round(pct)))

    if ref_min is not None and ref_min > 0:
        pct = (ref_min / value) * (100 / 1.2) if value > 0 else 100
        return min(100, max(3, round(pct)))

    return 50


def determine_flag(
    value: float,
    ref_min: float | None,
    ref_max: float | None,
    caution_band: tuple[float, float] | None = None,
) -> str:
    """
    Return "Normal", "Caution", or "See Doctor".
    FIX: guard against ref_min == 0 to prevent ZeroDivisionError.
    """
    if ref_min is not None and ref_max is not None:
        if ref_min <= value <= ref_max:
            return "Normal"
        if caution_band and caution_band[0] <= value <= caution_band[1]:
            return "Caution"
        # FIX: avoid division by zero when ref_min is 0
        if value < ref_min:
            if ref_min == 0:
                return "Normal"
            deviation = (ref_min - value) / ref_min
        else:
            deviation = (value - ref_max) / ref_max if ref_max != 0 else 1.0
        return "Caution" if deviation <= 0.20 else "See Doctor"

    if ref_max is not None:
        if value <= ref_max:
            return "Normal"
        deviation = (value - ref_max) / ref_max if ref_max != 0 else 1.0
        return "Caution" if deviation <= 0.20 else "See Doctor"

    if ref_min is not None:
        if value >= ref_min:
            return "Normal"
        if ref_min == 0:
            return "Normal"
        deviation = (ref_min - value) / ref_min
        return "Caution" if deviation <= 0.20 else "See Doctor"

    return "Normal"


def apply_rules(test: dict, age: int, gender: str) -> dict:
    result = dict(test)
    result["unit"] = normalize_unit(test.get("unit"))

    ref_min, ref_max = parse_reference_range(test.get("reference_range"))

    if ref_min is None and ref_max is None:
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

    caution_band = None
    if any(x in test.get("test_name", "").lower() for x in ("hba1c", "a1c", "glycosylated")):
        caution_band = (5.6, 6.4)

    result["flag"]      = determine_flag(value, ref_min, ref_max, caution_band)
    result["gauge_pct"] = compute_gauge_pct(value, ref_min, ref_max)

    return result


def compare_two_reports(tests_old: list[dict], tests_new: list[dict]) -> list[dict]:
    """
    Diff two flagged test sets.
    Change values: "improved" | "worsened" | "stable" | "new" | "missing"
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
