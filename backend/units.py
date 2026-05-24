# units.py — medical unit alias normalisation
#
# WHAT THIS IS: a simple text-substitution dictionary.
# "gm%" and "g/dL" are the SAME unit written two different ways.
# This file just picks one consistent spelling so the rules engine
# always sees the same string when comparing ranges.
#
# WHAT THIS IS NOT: chemical unit conversion (mmol/L → mg/dL).
# That would require molecular weight maths per analyte — biochemistry-thesis territory.
# That work is documented in the README under "Future Architecture Scope."
# For this project the printed reference range comes from the PDF itself,
# so the units already match and no conversion is required.
#
# INTERVIEW TALKING POINT:
# "I separated alias normalisation from unit conversion.
#  Alias normalisation is deterministic string mapping — safe to hardcode.
#  Conversion requires molecular weights per analyte — I documented that
#  as the next architectural step using the pint library."
 
MEDICAL_ALIASES: dict[str, str] = {
    # Haemoglobin / protein concentrations
    "gm%":          "g/dL",
    "gm/dl":        "g/dL",
    "gm/100ml":     "g/dL",
    "grams%":       "g/dL",
    "grams/dl":     "g/dL",
    "g%":           "g/dL",
 
    # Mass concentrations
    "mg%":          "mg/dL",
    "mg/100ml":     "mg/dL",
    "mgm/dl":       "mg/dL",
    "mgm%":         "mg/dL",
 
    # Electrolytes
    "meq/l":        "mEq/L",
    "milli eq/l":   "mEq/L",
    "millieq/l":    "mEq/L",
    "mmol/l":       "mmol/L",   # keep as-is — conversion handled separately if needed
 
    # Enzyme activity
    "iu/l":         "U/L",
    "u/litre":      "U/L",
    "units/l":      "U/L",
    "u/liter":      "U/L",
    "ku/l":         "kU/L",
 
    # Hormones
    "miu/ml":       "mIU/mL",
    "miu/l":        "mIU/L",
    "mu/l":         "mU/L",
    "uiu/ml":       "μIU/mL",
 
    # Vitamins / micronutrients
    "ng/dl":        "ng/dL",
    "pg/dl":        "pg/dL",
    "nmol/l":       "nmol/L",
 
    # Blood cell counts — Indian labs use many spellings
    "cells/cumm":   "cells/μL",
    "cells/mm3":    "cells/μL",
    "cells/cmm":    "cells/μL",
    "/cumm":        "/μL",
    "/cmm":         "/μL",
    "thou/ul":      "×10³/μL",
    "thou/µl":      "×10³/μL",
    "k/ul":         "×10³/μL",
    "k/µl":         "×10³/μL",
    "10^3/ul":      "×10³/μL",
    "10*3/ul":      "×10³/μL",
    "million/ul":   "×10⁶/μL",
    "million/µl":   "×10⁶/μL",
    "mill/ul":      "×10⁶/μL",
    "10^6/ul":      "×10⁶/μL",
    "10*6/ul":      "×10⁶/μL",
 
    # Volume (MCV, RDW etc.)
    "fl":           "fL",
    "femtolitre":   "fL",
    "femtoliter":   "fL",
 
    # Misc
    "percent":      "%",
    "ratio":        "ratio",
    "titre":        "titre",
    "titer":        "titre",
}
 
 
def normalize_unit_alias(unit: str | None) -> str | None:
    """
    Normalise a unit string to a consistent standard spelling.
 
    Lookup is case-insensitive and strips whitespace.
    Unknown units pass through unchanged — we never discard data.
 
    Example:
        "gm%"  → "g/dL"
        "IU/L" → "U/L"
        "mg/dL" → "mg/dL"  (already standard, unchanged)
        "HbA1c" → "HbA1c"  (not a unit, passes through)
    """
    if not unit:
        return unit
    key = unit.strip().lower()
    return MEDICAL_ALIASES.get(key, unit.strip())
 