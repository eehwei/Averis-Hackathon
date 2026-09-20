import unittest

from loader import Inbox
from sdoc_pipeline import FIELDS, compare_documents, parse_document, process


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

    def test_non_text_comparison_is_reviewed(self):
        result = process(self.inbox)["email_059"]
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(result["review_reason"], "unreadable")

    def test_submission_covers_every_email(self):
        results = process(self.inbox)
        self.assertEqual(set(results), {email["email_id"] for email in self.inbox})


if __name__ == "__main__":
    unittest.main()