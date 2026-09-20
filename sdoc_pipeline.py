"""Deterministic baseline for the shipping document verification task."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loader import Inbox


FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

REVIEW_REASONS = {"wrong_doc_type", "missing_attachment", "unreadable", "missing_value"}


@dataclass
class ParsedDocument:
    kind: str
    values: dict[str, str]
    evidence: dict[str, str]


def _clean(value: str) -> str:
    value = value.upper().replace("毛重", "")
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^A-Z0-9]+", "", value)


def _number(value: str) -> str:
    match = re.search(r"\d[\d,\.]*", value)
    if not match:
        return ""
    return re.sub(r"[,\.](?=\d{3}(?:\D|$))", "", match.group())


def _container_count(value: str) -> str:
    match = re.search(r"\d[\d,]*", value)
    return match.group().replace(",", "") if match else ""


def _label_for(line: str) -> tuple[str | None, str]:
    label, _, value = line.partition(":")
    label = _clean(re.sub(r"\([^)]*\)", "", label))
    aliases = {
        "SHIPPER": "shipper",
        "SHIPPEREXPORTER": "shipper",
        "SHIPPERPRINCIPALORSELLER": "shipper",
        "CONSIGNEE": "consignee",
        "CONSIGNEENONNEGOTIABLE": "consignee",
        "TOTHEORDEROF": "consignee",
        "NOTIFY": "notify_party",
        "NOTIFYPARTY": "notify_party",
        "NOTIFYPARTYINTERMEDIATECONSIGNEE": "notify_party",
        "PORTOFLOADING": "port_of_loading",
        "POL": "port_of_loading",
        "LOADPORT": "port_of_loading",
        "DISCHARGEPORT": "port_of_discharge",
        "PORTOFDISCHARGE": "port_of_discharge",
        "POD": "port_of_discharge",
        "NOOFCONTAINERS": "container_count",
        "NOOFCONTAINERSORPACKAGES": "container_count",
        "TOTALCONTAINERS": "container_count",
        "CONTAINERCOUNT": "container_count",
        "GROSSWEIGHTKG": "gross_weight_kg",
        "GROSSWT": "gross_weight_kg",
        "GROSSWTKGS": "gross_weight_kg",
        "GROSSWEIGHT": "gross_weight_kg",
    }
    return aliases.get(label), value.strip()


def parse_document(text: str) -> ParsedDocument:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kind = "BL" if any("BILL OF LADING" in line.upper() for line in lines[:3]) else "SI"
    values: dict[str, str] = {}
    evidence: dict[str, str] = {}
    current: str | None = None

    for line in lines:
        field, value = _label_for(line)
        if field:
            values[field] = value
            evidence[field] = line
            current = field if field in {"shipper", "consignee", "notify_party"} else None
        elif current and (line.startswith(";") or line.startswith("#") or "," in line):
            values[current] = f"{values[current]} {line}".strip()
            evidence[current] = f"{evidence[current]} {line}"

    return ParsedDocument(kind, values, evidence)


def _normalized(field: str, value: str) -> str:
    if field in {"container_count"}:
        return _container_count(value)
    if field == "gross_weight_kg":
        return _number(value)
    return _clean(value)


def classify(email: dict[str, Any]) -> str:
    subject = str(email.get("subject", "")).lower()
    body = str(email.get("body", "")).lower()
    text = f"{subject}\n{body}"
    attachments = [str(path).lower() for path in email.get("attachments", [])]

    comparison_terms = (
        "draft bl",
        "bill of lading",
        "check the details",
        "check the draft",
        "verify the bl",
        "confirm docs",
        "matches the si",
    )
    if len(attachments) >= 2 and any(term in text for term in comparison_terms):
        return "BL_COMPARISON"
    if "invoice" in text or "billing" in text or "payment" in text:
        return "INVOICE_QUERY"
    if any(term in text for term in ("prepare the si", "new shipping instruction", "create si")):
        return "SI_REQUEST"
    if any(term in text for term in ("unsubscribe", "winner", "crypto", "casino", "viagra")):
        return "SPAM"
    return "GENERAL"


def _result(category: str, status: str = "OK", *, reason: str | None = None, defects: list[str] | None = None) -> dict[str, Any]:
    defects = defects or []
    return {
        "category": category,
        "status": status,
        "review_reason": reason,
        "defect_fields": defects,
        "has_defect": bool(defects),
    }


def compare_documents(si: ParsedDocument, bl: ParsedDocument) -> dict[str, Any]:
    if si.kind != "SI" or bl.kind != "BL":
        return _result("BL_COMPARISON", "NEEDS_REVIEW", reason="wrong_doc_type")
    missing = [field for field in FIELDS if not si.values.get(field) or not bl.values.get(field)]
    if missing:
        return _result("BL_COMPARISON", "NEEDS_REVIEW", reason="missing_value")
    defects = [
        field for field in FIELDS
        if _normalized(field, si.values[field]) != _normalized(field, bl.values[field])
    ]
    return _result("BL_COMPARISON", "MISMATCH" if defects else "OK", defects=defects)


def process(inbox: Inbox) -> dict[str, dict[str, Any]]:
    submission: dict[str, dict[str, Any]] = {}
    for email in inbox:
        category = classify(email)
        if category != "BL_COMPARISON":
            submission[email["email_id"]] = _result(category)
            continue

        attachments = [str(path) for path in email.get("attachments", [])]
        si_paths = [path for path in attachments if path.lower().endswith("_si.txt")]
        bl_paths = [path for path in attachments if path.lower().endswith("_bl.txt")]
        if not si_paths or not bl_paths:
            reason = "missing_attachment" if len(attachments) < 2 else "unreadable"
            submission[email["email_id"]] = _result(category, "NEEDS_REVIEW", reason=reason)
            continue
        try:
            si = parse_document(inbox.read_text(si_paths[0]))
            bl = parse_document(inbox.read_text(bl_paths[0]))
        except (OSError, UnicodeError):
            submission[email["email_id"]] = _result(category, "NEEDS_REVIEW", reason="unreadable")
            continue
        submission[email["email_id"]] = compare_documents(si, bl)
    return submission


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Generate a shipping document submission.")
    parser.add_argument("source", nargs="?", default=".", help="Dataset folder or Inbox HTTP URL")
    parser.add_argument("-o", "--output", default="submission.json")
    args = parser.parse_args()
    submission = process(Inbox(args.source))
    Path(args.output).write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(submission)} email results to {args.output}")


if __name__ == "__main__":
    main()