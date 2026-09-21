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
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - only matters if dependency is missing
    requests = None


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


def _is_missing_field_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def build_submission_payload(doc_id: str, si_data: dict[str, Any], bl_data: dict[str, Any]) -> dict[str, Any]:
    """Build a compliance payload for a document.

    Status is set to NEEDS_REVIEW when the SI/BL data has any field mismatch or
    missing value. Otherwise it passes.
    """
    mismatches = compare_si_bl(si_data, bl_data)

    missing_fields = [
        field
        for field in COMPARE_FIELDS
        if field not in si_data or field not in bl_data
        or _is_missing_field_value(si_data.get(field))
        or _is_missing_field_value(bl_data.get(field))
    ]

    status = "PASSED" if not mismatches and not missing_fields else "NEEDS_REVIEW"

    return {
        "doc_id": doc_id,
        "status": status,
        "mismatches": mismatches,
        "missing_fields": missing_fields,
        "checked_fields": COMPARE_FIELDS,
    }


def submit_to_api(payload: dict[str, Any], endpoint_url: str):
    """POST the compliance JSON to the submit endpoint."""
    if requests is None:
        raise RuntimeError("requests is required for submit_to_api(). Install it with: pip install requests")

    submit_url = endpoint_url.rstrip("/")
    if not submit_url.endswith("/submit"):
        submit_url = f"{submit_url}/submit"

    response = requests.post(submit_url, json=payload, timeout=30)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text


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

import csv
import json


def save_outputs(results, json_path="output.json", csv_path="output.csv"):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"JSON Output saved to {json_path}")

   
    if results:
        keys = results[0].keys()
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"CSV Output saved to {csv_path}")

if __name__ == "__main__":
    
    test_data = [
        {"email_id": "001", "status": "VERIFIED", "discrepancies": "None"},
        {"email_id": "002", "status": "NEEDS_REVIEW", "discrepancies": "Weight mismatch"}
    ]
   
    save_outputs(test_data, "test_output.json", "test_output.csv")
    