import os
from unittest.mock import MagicMock

import pytest

from classify import classify_email


def _mock_client(category: str) -> MagicMock:
    """Build a fake anthropic client whose messages.parse() returns `category`."""
    client = MagicMock()
    response = MagicMock()
    response.parsed_output.category = category
    client.messages.parse.return_value = response
    return client


BL_COMPARISON_EMAIL = {
    "email_id": "email_test_001",
    "from": "docs@example-trading.com",
    "subject": "TO CONFIRM DOCS _ 5AAA-00111 _ ROTTERDAM_NETHERLANDS _ ACME TRADING BV",
    "body": (
        "Hi team,\n\nAttached are the SI and draft BL for OC 5AAA-00111. "
        "Please check the details and confirm.\n\nBest Regards,\nDocs Team"
    ),
    "attachments": [
        "attachments/email_test_001_SI.txt",
        "attachments/email_test_001_BL.txt",
    ],
}

SPAM_EMAIL = {
    "email_id": "email_test_002",
    "from": "info@crypto-invest.net",
    "subject": "Increase your shipping revenue with this ONE weird trick",
    "body": (
        "Dear user, your mailbox has exceeded its storage limit. Verify your "
        "account within 24 hours to avoid deactivation: http://webmail-verify.co"
    ),
    "attachments": [],
}


@pytest.mark.parametrize(
    "email, expected_category",
    [
        (BL_COMPARISON_EMAIL, "BL_COMPARISON"),
        (SPAM_EMAIL, "SPAM"),
    ],
)
def test_classify_email_returns_the_model_category(email, expected_category):
    client = _mock_client(expected_category)

    result = classify_email(email, client=client)

    assert result == expected_category


def test_classify_email_calls_the_api_with_the_expected_model_and_prompt():
    client = _mock_client("BL_COMPARISON")

    classify_email(BL_COMPARISON_EMAIL, client=client)

    client.messages.parse.assert_called_once()
    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    prompt = kwargs["messages"][0]["content"]
    assert BL_COMPARISON_EMAIL["subject"] in prompt
    assert BL_COMPARISON_EMAIL["from"] in prompt
    assert "attachments/email_test_001_SI.txt" in prompt


def test_classify_email_marks_missing_attachments_as_none():
    client = _mock_client("SPAM")

    classify_email(SPAM_EMAIL, client=client)

    _, kwargs = client.messages.parse.call_args
    prompt = kwargs["messages"][0]["content"]
    assert "Attachments: (none)" in prompt


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a real ANTHROPIC_API_KEY to call the live API",
)
def test_classify_email_live_api_classifies_a_real_bl_comparison_email():
    """Integration smoke test - hits the real Claude API. Costs a small amount
    and is skipped automatically unless ANTHROPIC_API_KEY is set."""
    result = classify_email(BL_COMPARISON_EMAIL)
    assert result == "BL_COMPARISON"
