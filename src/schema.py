"""Shared data types for the SDOC email classification pipeline.

See the hackathon bundle README (sdoc-hackathon-bundle/README.md) for the
full task description these types are modeled on.
"""

from typing import Dict, Iterable, List, Literal, Mapping, Optional, Sequence, TypedDict

EmailCategory = Literal[
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
]

CATEGORIES: tuple = (
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
)

Email = TypedDict(
    "Email",
    {
        "email_id": str,
        "from": str,
        "subject": str,
        "body": str,
        "attachments": List[str],
    },
)   

Status = Literal[
    "OK",
    "MISMATCH",
    "NEEDS_REVIEW",
]

STATUSES: tuple = (
    "OK",
    "MISMATCH",
    "NEEDS_REVIEW",
)

ReviewReason = Literal[
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
]

REVIEW_REASONS: tuple = (
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
)

# The 7 fields compared between the SI and the draft BL. The two documents often
# label the same field differently ("Port of Loading" vs "Load Port") - these are
# the canonical names, aligned by meaning rather than by header text.
ComparisonField = Literal[
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

COMPARISON_FIELDS: tuple = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)


class SubmissionEntry(TypedDict):
    """One email's result, shaped exactly like an entry in sample_submission.json."""

    category: EmailCategory
    status: Status
    review_reason: Optional[ReviewReason]
    defect_fields: List[ComparisonField]
    has_defect: bool


def build_entry(
    category: EmailCategory,
    *,
    status: Status = "OK",
    review_reason: Optional[ReviewReason] = None,
    defect_fields: Optional[Sequence[ComparisonField]] = None,
) -> SubmissionEntry:
    """Build one submission entry, keeping the status-dependent fields consistent.

    `has_defect` is derived from `status` so the two can never disagree, and
    fields that don't apply to the status are dropped: `defect_fields` is kept
    only for MISMATCH, `review_reason` only for NEEDS_REVIEW. Unknown category /
    status / field names raise, since a typo there silently costs score.
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category!r}")
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r}")

    fields = list(defect_fields or [])
    unknown = [field for field in fields if field not in COMPARISON_FIELDS]
    if unknown:
        raise ValueError(f"unknown defect_fields: {unknown}")

    if status == "MISMATCH":
        if not fields:
            raise ValueError("MISMATCH needs at least one entry in defect_fields")
        review_reason = None
    elif status == "NEEDS_REVIEW":
        if review_reason not in REVIEW_REASONS:
            raise ValueError(
                f"NEEDS_REVIEW needs a review_reason, got {review_reason!r}"
            )
        fields = []
    else:  # OK
        review_reason = None
        fields = []

    return {
        "category": category,
        "status": status,
        "review_reason": review_reason,
        "defect_fields": fields,
        "has_defect": status == "MISMATCH",
    }


def build_submission(
    email_ids: Iterable[str],
    results: Mapping[str, SubmissionEntry],
) -> Dict[str, SubmissionEntry]:
    """Assemble the full submission dict, one entry per email_id.

    The scorer needs every email_id from the inbox present, so ids missing from
    `results` fall back to a neutral GENERAL/OK entry instead of being dropped.
    """
    ids = list(email_ids)

    unexpected = sorted(set(results) - set(ids))
    if unexpected:
        raise ValueError(f"results contain unknown email_ids: {unexpected}")

    return {
        email_id: results.get(email_id) or build_entry("GENERAL") for email_id in ids
    }
