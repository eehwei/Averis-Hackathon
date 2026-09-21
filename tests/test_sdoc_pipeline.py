import unittest

from loader import Inbox
from sdoc_pipeline import FIELDS, extract_attachment, parse_document, process


class SdocPipelineTests(unittest.TestCase):
    def setUp(self):
        self.inbox = Inbox(".")

    def test_parses_label_aliases(self):
        document = parse_document(self.inbox.read_text("attachments/email_001_BL.txt"))
        self.assertEqual(document.kind, "BL")
        self.assertEqual(set(document.values), set(FIELDS))

    def test_representative_comparisons(self):
        results = process(self.inbox)
        self.assertEqual(results["email_001"]["status"], "OK")
        self.assertEqual(results["email_013"]["defect_fields"], ["port_of_discharge"])
        self.assertEqual(
            results["email_031"]["defect_fields"],
            ["container_count", "gross_weight_kg"],
        )

    def test_scanned_pdf_comparison_is_reviewed(self):
        result = process(self.inbox)["email_059"]
        self.assertEqual(result["status"], "OK")

        scanned = process(self.inbox)["email_512"]
        self.assertEqual(scanned["status"], "NEEDS_REVIEW")
        self.assertEqual(scanned["review_reason"], "unreadable")

    def test_extractable_pdf_is_processed(self):
        result = process(self.inbox)["email_059"]
        self.assertNotEqual(result["review_reason"], "missing_attachment")

    def test_pdf_adapter_returns_a_document(self):
        content = self.inbox.read_bytes("attachments/email_059_SI.pdf")
        result = extract_attachment("attachments/email_059_SI.pdf", content)
        self.assertEqual(result.format, "pdf")
        self.assertIsNotNone(result.document)

    def test_xlsx_and_docx_adapters_extract_fields(self):
        for path in (
            "attachments/email_005_SI.xlsx",
            "attachments/email_005_BL.xlsx",
            "attachments/email_055_BL.docx",
        ):
            result = extract_attachment(path, self.inbox.read_bytes(path))
            self.assertIsNotNone(result.document, path)
            self.assertEqual(set(result.document.values), set(FIELDS))

    def test_mixed_office_pair_is_compared(self):
        result = process(self.inbox)["email_055"]
        self.assertEqual(result["status"], "OK")

    def test_injected_classifier_is_used(self):
        calls = []

        def classifier(email):
            calls.append(email["email_id"])
            return "GENERAL"

        results = process(self.inbox, classifier=classifier)
        self.assertEqual(set(calls), {email["email_id"] for email in self.inbox})
        self.assertTrue(all(result["category"] == "GENERAL" for result in results.values()))

    def test_classifier_failure_falls_back_to_rules(self):
        def classifier(_email):
            raise RuntimeError("provider unavailable")

        result = process(self.inbox, classifier=classifier)["email_001"]
        self.assertEqual(result["category"], "BL_COMPARISON")

    def test_submission_covers_every_email(self):
        results = process(self.inbox)
        self.assertEqual(set(results), {email["email_id"] for email in self.inbox})

    def test_max_seconds_zero_skips_the_classifier_entirely(self):
        """An already-exhausted time budget should fall back to the
        deterministic classifier for every email without ever calling the
        (would-be) LLM classifier, so a slow/unavailable API can't stall the
        run."""
        calls = []

        def classifier(email):
            calls.append(email["email_id"])
            return "GENERAL"

        results = process(self.inbox, classifier=classifier, max_seconds=0)

        self.assertEqual(calls, [])
        self.assertEqual(results["email_001"]["category"], "BL_COMPARISON")

    def test_max_seconds_none_keeps_using_the_classifier_throughout(self):
        calls = []

        def classifier(email):
            calls.append(email["email_id"])
            return "GENERAL"

        results = process(self.inbox, classifier=classifier, max_seconds=None)

        self.assertEqual(set(calls), {email["email_id"] for email in self.inbox})
        self.assertTrue(all(result["category"] == "GENERAL" for result in results.values()))


if __name__ == "__main__":
    unittest.main()