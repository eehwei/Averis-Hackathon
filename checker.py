"""Utilities for comparing extracted SI and BL JSON records.

This module normalizes and compares the seven comparison fields used for the
SI-vs-BL check:

- shipper
- consignee
- notify_party
- port_of_loading
- port_of_discharge
- container_count
- gross_weight_kg

It returns a list of field names that do not match after normalization.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable


COMPARE_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return " ".join(str(value).strip().split())


def normalize_port_name(value: Any) -> str:
    """Normalize a port value to a stable uppercase string.

    Rules used here:
    - convert to text
    - strip leading/trailing whitespace
    - collapse redundant spaces
    - uppercase for comparison
    """
    return _clean_text(value).upper()


def normalize_gross_weight_kg(value: Any) -> int | float | None:
    """Normalize a weight into gross_weight_kg.

    Examples:
    - 2000 -> 2000
    - 2000.0 -> 2000
    - "2,000 kg" -> 2000
    - "2000.456" -> 2000.456
    - "2000.000" -> 2000
    """
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().upper()
        text = text.replace(",", "")
        text = text.replace("KG", "").replace("KGS", "").strip()
        match = re.search(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?", text)
        if not match:
            return None
        number = float(match.group(0))

    rounded = round(number, 3)
    if math.isclose(rounded, round(rounded), rel_tol=1e-9, abs_tol=1e-9):
        return int(round(rounded))
    return rounded


def normalize_container_count(value: Any) -> int | str | None:
    """Normalize integer-like container counts."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isclose(value, round(value), rel_tol=1e-9, abs_tol=1e-9) else value

    text = _clean_text(value)
    match = re.search(r"[-+]?\d+", text)
    if not match:
        return text
    number = int(match.group(0))
    return number


def _normalize_field(field_name: str, value: Any) -> Any:
    if field_name in {"port_of_loading", "port_of_discharge"}:
        return normalize_port_name(value)
    if field_name == "gross_weight_kg":
        return normalize_gross_weight_kg(value)
    if field_name == "container_count":
        return normalize_container_count(value)
    if value is None:
        return ""
    return _clean_text(value)


def _field_value(record: dict[str, Any] | None, field_name: str) -> Any:
    if not isinstance(record, dict):
        return None
    if field_name in record:
        return record.get(field_name)
    return None


def compare_si_bl(si_data: dict[str, Any], bl_data: dict[str, Any]) -> list[str]:
    """Return the field names that differ between SI and BL data.

    Example:
        mismatches = compare_si_bl(si_data, bl_data)
        # => ["consignee", "gross_weight_kg"]
    """
    mismatches: list[str] = []

    for field in COMPARE_FIELDS:
        si_value = _field_value(si_data, field)
        bl_value = _field_value(bl_data, field)

        normalized_si = _normalize_field(field, si_value)
        normalized_bl = _normalize_field(field, bl_value)

        if normalized_si != normalized_bl:
            mismatches.append(field)

    return mismatches


def compare_si_vs_bl(si_data: dict[str, Any], bl_data: dict[str, Any]) -> list[str]:
    """Alias for compare_si_bl()."""
    return compare_si_bl(si_data, bl_data)


if __name__ == "__main__":
    sample_si = {
        "shipper": "APRIL FINE PAPER TRADING",
        "consignee": "ACME IMPORTS",
        "notify_party": "NOTIFY PARTNER LTD",
        "port_of_loading": " Singapore ",
        "port_of_discharge": "Dubai",
        "container_count": 2,
        "gross_weight_kg": "2000.50 kg",
    }
    sample_bl = {
        "shipper": "APRIL FINE PAPER TRADING",
        "consignee": "ACME IMPORTS INC",
        "notify_party": "NOTIFY PARTNER LTD",
        "port_of_loading": "SINGAPORE",
        "port_of_discharge": "DUBAI",
        "container_count": 2,
        "gross_weight_kg": 2000.5,
    }

    print(compare_si_bl(sample_si, sample_bl))
