import json
from pathlib import Path

import pytest

from schema import (
    CATEGORIES,
    COMPARISON_FIELDS,
    REVIEW_REASONS,
    STATUSES,
    build_entry,
    build_submission,
)

BUNDLE = Path(__file__).resolve().parents[1]


def test_the_vocabularies_match_the_bundle_spec():
    assert STATUSES == ("OK", "MISMATCH", "NEEDS_REVIEW")
    assert REVIEW_REASONS == (
        "wrong_doc_type",
        "missing_attachment",
        "unreadable",
        "missing_value",
    )
    assert COMPARISON_FIELDS == (
        "shipper",
        "consignee",
        "notify_party",
        "port_of_loading",
        "port_of_discharge",
        "container_count",
        "gross_weight_kg",
    )


def test_an_ok_entry_matches_the_sample_submission_shape():
    sample = json.loads((BUNDLE / "sample_submission.json").read_text())
    expected = sample["email_001"]

    assert build_entry("GENERAL") == expected


def test_a_mismatch_entry_carries_the_defect_fields():
    entry = build_entry(
        "BL_COMPARISON", status="MISMATCH", defect_fields=["consignee"]
    )

    assert entry == {
        "category": "BL_COMPARISON",
        "status": "MISMATCH",
        "review_reason": None,
        "defect_fields": ["consignee"],
        "has_defect": True,
    }


def test_a_needs_review_entry_carries_the_reason_and_no_defects():
    entry = build_entry(
        "BL_COMPARISON", status="NEEDS_REVIEW", review_reason="missing_attachment"
    )

    assert entry["review_reason"] == "missing_attachment"
    assert entry["defect_fields"] == []
    assert entry["has_defect"] is False


def test_fields_that_do_not_apply_to_the_status_are_dropped():
    entry = build_entry(
        "BL_COMPARISON",
        status="OK",
        review_reason="unreadable",
        defect_fields=["shipper"],
    )

    assert entry["review_reason"] is None
    assert entry["defect_fields"] == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "NOT_A_CATEGORY"},
        {"category": "GENERAL", "status": "NOT_A_STATUS"},
        {"category": "BL_COMPARISON", "status": "MISMATCH"},
        {"category": "BL_COMPARISON", "status": "NEEDS_REVIEW"},
        {
            "category": "BL_COMPARISON",
            "status": "MISMATCH",
            "defect_fields": ["vessel_name"],
        },
    ],
)
def test_inconsistent_entries_are_rejected(kwargs):
    category = kwargs.pop("category")
    with pytest.raises(ValueError):
        build_entry(category, **kwargs)


def test_build_submission_covers_every_inbox_id():
    ids = sorted(p.stem for p in (BUNDLE / "inbox").glob("email_*.json"))
    results = {
        "email_001": build_entry(
            "BL_COMPARISON", status="MISMATCH", defect_fields=["consignee"]
        )
    }

    submission = build_submission(ids, results)

    assert set(submission) == set(ids)
    assert submission["email_001"]["has_defect"] is True
    assert submission["email_002"] == build_entry("GENERAL")


def test_build_submission_rejects_ids_outside_the_inbox():
    with pytest.raises(ValueError):
        build_submission(["email_001"], {"email_999": build_entry("GENERAL")})


def test_a_default_submission_equals_the_sample_submission():
    sample = json.loads((BUNDLE / "sample_submission.json").read_text())

    submission = build_submission(sample.keys(), {})

    assert submission == sample
