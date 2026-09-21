"""Deterministic baseline for the shipping document verification task."""

from __future__ import annotations

import re
import importlib
import os
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from loader import Inbox
from schema import build_entry

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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


@dataclass
class ExtractionResult:
    document: ParsedDocument | None
    format: str
    error: str | None = None


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
    label = re.sub(r"[\(\（][^\)\）]*[\)\）]", "", label)
    inline_aliases = (
        (r"^CONSIGNEE(?:\s|$)", "consignee"),
        (r"^NOTIFY PARTY(?:\s|$)", "notify_party"),
        (r"^LOAD PORT(?:\s|$)", "port_of_loading"),
        (r"^PORT OF DISCHARGE(?:\s|$)", "port_of_discharge"),
    )
    for pattern, field in inline_aliases:
        match = re.match(pattern, label, flags=re.IGNORECASE)
        if match and not value:
            return field, label[match.end():].strip()
    label = _clean(label)
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
        "TOTALGROSSWT": "gross_weight_kg",
        "TOTALGROSSWEIGHT": "gross_weight_kg",
    }
    return aliases.get(label), value.strip()


def parse_document(text: str) -> ParsedDocument:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = " ".join(lines[:3]).upper()
    kind = "SI" if "INSTRUCTION" in header and "DRAFT" not in header else "BL"
    values: dict[str, str] = {}
    evidence: dict[str, str] = {}
    current: str | None = None

    for line in lines:
        field, value = _label_for(line)
        if field:
            values[field] = value
            evidence[field] = line
            current = field if not value or field in {"shipper", "consignee", "notify_party"} else None
        elif current:
            values[current] = f"{values[current]} {line}".strip()
            evidence[current] = f"{evidence[current]} {line}"
            if current not in {"shipper", "consignee", "notify_party"}:
                current = None

    return ParsedDocument(kind, values, evidence)


def _document_from_text(text: str, format: str) -> ExtractionResult:
    if not text.strip():
        return ExtractionResult(None, format, "unreadable")
    return ExtractionResult(parse_document(text), format)


def _ooxml_text(content: bytes, filename: str) -> str:
    namespace = {"main": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read(filename))
    return "\n".join(
        " ".join(node.text or "" for node in paragraph.findall(".//main:t", namespace)).strip()
        for paragraph in root.findall(".//main:p", namespace)
    )


def _xlsx_text(content: bytes) -> str:
    main_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationships_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(BytesIO(content)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()).strip() for node in root.findall(f"{{{main_namespace}}}si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships
        }
        parts = []
        for sheet in workbook.findall(f"{{{main_namespace}}}sheets/{{{main_namespace}}}sheet"):
            relationship_id = sheet.attrib.get(f"{{{relationships_namespace}}}id")
            target = targets.get(relationship_id, "")
            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = f"xl/{sheet_path}"
            root = ElementTree.fromstring(archive.read(sheet_path))
            for row in root.findall(f".//{{{main_namespace}}}row"):
                cells = []
                for cell in row.findall(f"{{{main_namespace}}}c"):
                    value = cell.find(f"{{{main_namespace}}}v")
                    if value is None:
                        inline = cell.find(f"{{{main_namespace}}}is")
                        cells.append("".join(inline.itertext()).strip() if inline is not None else "")
                    elif cell.attrib.get("t") == "s":
                        cells.append(shared[int(value.text)])
                    else:
                        cells.append(value.text or "")
                cells = [cell.strip() for cell in cells if cell.strip()]
                if len(cells) >= 2:
                    parts.append(f"{cells[0]}: {' '.join(cells[1:])}")
                elif cells:
                    parts.append(cells[0])
    return "\n".join(parts)


def extract_attachment(path: str, content: bytes) -> ExtractionResult:
    """Convert a supported attachment into the shared semantic document model."""
    suffix = Path(path).suffix.lower()
    if suffix == ".txt":
        return _document_from_text(content.decode("utf-8", errors="replace"), "txt")
    if suffix == ".pdf":
        try:
            try:
                fitz = importlib.import_module("fitz")
                text = "\n".join(page.get_text() for page in fitz.open(stream=content, filetype="pdf"))
            except ImportError:
                from pypdf import PdfReader

                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        except Exception:
            return ExtractionResult(None, "pdf", "unreadable")
        return _document_from_text(text, "pdf")
    if suffix == ".docx":
        try:
            from docx import Document

            document = Document(BytesIO(content))
            parts = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if len(cells) >= 2:
                        parts.append(f"{cells[0]}: {cells[1]}")
                    elif cells:
                        parts.append(cells[0])
            return _document_from_text("\n".join(parts), "docx")
        except ImportError:
            try:
                return _document_from_text(_ooxml_text(content, "word/document.xml"), "docx")
            except (BadZipFile, KeyError, ElementTree.ParseError):
                return ExtractionResult(None, "docx", "unreadable")
        except Exception:
            return ExtractionResult(None, "docx", "unreadable")
    if suffix == ".xlsx":
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            parts = []
            for worksheet in workbook.worksheets:
                for row in worksheet.iter_rows(values_only=True):
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if len(cells) >= 2:
                        parts.append(f"{cells[0]}: {' '.join(cells[1:])}")
                    elif cells:
                        parts.append(cells[0])
            return _document_from_text("\n".join(parts), "xlsx")
        except ImportError:
            try:
                return _document_from_text(_xlsx_text(content), "xlsx")
            except (BadZipFile, KeyError, ValueError, ElementTree.ParseError):
                return ExtractionResult(None, "xlsx", "unreadable")
        except Exception:
            return ExtractionResult(None, "xlsx", "unreadable")
    return ExtractionResult(None, suffix.lstrip(".") or "unknown", "unreadable")


def _normalized(field: str, value: str) -> str:
    if field in {"container_count"}:
        return _container_count(value)
    if field == "gross_weight_kg":
        return _number(value)
    return _clean(value)


def deterministic_classify(email: dict[str, Any]) -> str:
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


def classify(email: dict[str, Any]) -> str:
    """Backward-compatible name for the deterministic classifier."""
    return deterministic_classify(email)


def _result(category: str, status: str = "OK", *, reason: str | None = None, defects: list[str] | None = None) -> dict[str, Any]:
    return build_entry(
        category,
        status=status,
        review_reason=reason,
        defect_fields=defects,
    )


def _llm_classify(email: dict[str, Any]) -> str:
    from classify import classify_email

    return classify_email(email)


def classify_with_fallback(
    email: dict[str, Any], classifier: Any = None
) -> str:
    """Prefer the configured LLM classifier, with deterministic fallback."""
    selected = classifier
    if selected is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        llm_enabled = (
            os.getenv("SDOC_CLASSIFIER", "").lower() == "llm"
            and api_key
            and not api_key.lower().startswith("replace-with-")
        )
        selected = _llm_classify if llm_enabled else None
    if selected is None:
        return deterministic_classify(email)
    try:
        category = selected(email)
        if category not in {"BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"}:
            raise ValueError(f"unknown email category: {category!r}")
        return category
    except Exception:
        return deterministic_classify(email)


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


def process(inbox: Inbox, classifier: Any = None) -> dict[str, dict[str, Any]]:
    submission: dict[str, dict[str, Any]] = {}
    for email in inbox:
        category = classify_with_fallback(email, classifier)
        if category != "BL_COMPARISON":
            submission[email["email_id"]] = _result(category)
            continue

        attachments = [str(path) for path in email.get("attachments", [])]
        si_paths = [path for path in attachments if re.search(r"_si\.[^.]+$", path, re.IGNORECASE)]
        bl_paths = [path for path in attachments if re.search(r"_bl\.[^.]+$", path, re.IGNORECASE)]
        if not si_paths or not bl_paths:
            reason = "missing_attachment" if len(attachments) < 2 else "unreadable"
            submission[email["email_id"]] = _result(category, "NEEDS_REVIEW", reason=reason)
            continue
        si_extraction = extract_attachment(si_paths[0], inbox.read_bytes(si_paths[0]))
        bl_extraction = extract_attachment(bl_paths[0], inbox.read_bytes(bl_paths[0]))
        if not si_extraction.document or not bl_extraction.document:
            error = si_extraction.error or bl_extraction.error or "unreadable"
            reason = "missing_value" if error == "missing_value" else "unreadable"
            submission[email["email_id"]] = _result(category, "NEEDS_REVIEW", reason=reason)
            continue
        submission[email["email_id"]] = compare_documents(
            si_extraction.document,
            bl_extraction.document,
        )
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