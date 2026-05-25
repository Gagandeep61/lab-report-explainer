# ranges_fallback.py — minimal fallback reference ranges
# Used ONLY when the PDF does not print a reference range column.
# Priority: report's own printed range > this dict.
# Gender-aware where clinically relevant.

FALLBACK: dict[str, dict[str, tuple]] = {
    "hba1c":              {"male": (4.0, 5.6),   "female": (4.0, 5.6)},
    "glycosylated":       {"male": (4.0, 5.6),   "female": (4.0, 5.6)},
    "fasting glucose":    {"male": (70.0, 100.0), "female": (70.0, 100.0)},
    "fasting blood":      {"male": (70.0, 100.0), "female": (70.0, 100.0)},
    "glucose":            {"male": (70.0, 100.0), "female": (70.0, 100.0)},
    "total cholesterol":  {"male": (None, 200.0), "female": (None, 200.0)},
    "ldl":                {"male": (None, 100.0), "female": (None, 100.0)},
    "hdl":                {"male": (40.0, None),  "female": (50.0, None)},
    "triglyceride":       {"male": (None, 150.0), "female": (None, 150.0)},
    "hemoglobin":         {"male": (13.5, 17.5),  "female": (12.0, 15.5)},
    "haemoglobin":        {"male": (13.5, 17.5),  "female": (12.0, 15.5)},
    "wbc":                {"male": (4000, 11000),  "female": (4000, 11000)},
    "platelet":           {"male": (150000, 450000), "female": (150000, 450000)},
    "creatinine":         {"male": (0.7, 1.3),    "female": (0.6, 1.1)},
    "urea":               {"male": (15.0, 45.0),  "female": (15.0, 45.0)},
    "uric acid":          {"male": (3.4, 7.0),    "female": (2.4, 6.0)},
    "tsh":                {"male": (0.4, 4.0),    "female": (0.4, 4.0)},
    "vitamin d":          {"male": (30.0, 100.0), "female": (30.0, 100.0)},
    "vitamin b12":        {"male": (200, 900),    "female": (200, 900)},
    "alt":                {"male": (None, 56.0),  "female": (None, 45.0)},
    "sgpt":               {"male": (None, 56.0),  "female": (None, 45.0)},
    "ast":                {"male": (None, 40.0),  "female": (None, 40.0)},
    "sgot":               {"male": (None, 40.0),  "female": (None, 40.0)},
    "bilirubin":          {"male": (0.1, 1.2),    "female": (0.1, 1.2)},
    "ferritin":           {"male": (20, 250),     "female": (10, 120)},
    "iron":               {"male": (60, 170),     "female": (50, 170)},
    "calcium":            {"male": (8.5, 10.5),   "female": (8.5, 10.5)},
    "sodium":             {"male": (136, 145),    "female": (136, 145)},
    "potassium":          {"male": (3.5, 5.1),    "female": (3.5, 5.1)},
    "egfr":               {"male": (60, None),    "female": (60, None)},
}


def get_fallback_range(test_name: str, gender: str = "male") -> tuple | None:
    """Return (min, max) from fallback dict or None if not found."""
    key = test_name.strip().lower()
    g   = "female" if "female" in gender.lower() else "male"
    for pattern, genders in FALLBACK.items():
        if pattern in key:
            return genders.get(g)
    return None
