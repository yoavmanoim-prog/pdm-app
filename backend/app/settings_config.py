"""Per-repository configurable settings.

Settings live in Repository.settings (JSON). Missing/None values fall back to
the defaults here, so a repo that has never configured anything behaves exactly
as before.

Part-number format: the user enters a *sample* part number and the template is
derived from it — each letter becomes "A", each digit becomes "#", and every
other character is kept literal:

    "FW-PT-0001"  ->  template "AA-AA-####"  ->  matches 2 letters-2 letters-4 digits

That template then validates new part numbers and drives the auto-BOM
missing-detection. (The derivation can't tell "fixed letter" from "any letter",
so a literal letter in the format isn't expressible — letters are wildcards.)
"""
import re

DEFAULT_SETTINGS = {
    # None = no format configured: no part-number validation, and the auto-BOM
    # missing-detection uses its built-in pattern (legacy behaviour).
    "part_number_example": None,
    # revision code scheme used by the revision-sequence release rule:
    # "letters" -> A, B, C ...   "numbers" -> 001, 002, 003 ...
    "revision_scheme": "letters",
}

REVISION_SCHEMES = ("letters", "numbers")


def effective_settings(repo) -> dict:
    """Merge a repo's stored settings over the defaults."""
    result = dict(DEFAULT_SETTINGS)
    stored = getattr(repo, "settings", None) or {}
    for key in DEFAULT_SETTINGS:
        if stored.get(key) is not None:
            result[key] = stored[key]
    return result


def mask_from_example(example: str) -> str:
    """Derive the template/mask from a sample part number.
    Letters -> 'A', digits -> '#', everything else kept literal.
    e.g. "FW-PT-0001" -> "AA-AA-####"."""
    out = []
    for ch in example:
        if ch.isalpha():
            out.append("A")
        elif ch.isdigit():
            out.append("#")
        else:
            out.append(ch)
    return "".join(out)


def _mask_to_pattern(mask: str) -> str:
    """Translate a template (A/#/literal) into a regex body (no anchors)."""
    parts = []
    for ch in mask:
        if ch == "A":
            parts.append("[A-Za-z]")
        elif ch == "#":
            parts.append("[0-9]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def example_to_pattern(example: str) -> str:
    """Regex body that matches the same shape as the sample part number."""
    return _mask_to_pattern(mask_from_example(example))


def validate_example(example: str) -> str | None:
    """Return an error message if the sample part number is unusable, else None."""
    if not example or not example.strip():
        return "Enter a sample part number."
    if not any(c.isalnum() for c in example):
        return "Sample part number must contain at least one letter or digit."
    return None


def part_number_matches(example: str, value: str) -> bool:
    """True if value has the same shape as the sample (case-insensitive)."""
    return re.fullmatch(example_to_pattern(example), value or "", re.IGNORECASE) is not None
