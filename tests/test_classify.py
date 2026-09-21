import json
import os
from unittest.mock import MagicMock

import httpx
import pytest
from groq import AuthenticationError, InternalServerError

from classify import MODEL, SYSTEM_PROMPT, classify_email
from schema import CATEGORIES

_FAKE_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _server_error(status_code: int = 503) -> InternalServerError:
    response = httpx.Response(status_code, request=_FAKE_REQUEST, json={"error": {"message": "temporarily unavailable"}})
    return InternalServerError("temporarily unavailable", response=response, body=response.json())


def _client_error(status_code: int = 401) -> AuthenticationError:
    response = httpx.Response(status_code, request=_FAKE_REQUEST, json={"error": {"message": "invalid API key"}})
    return AuthenticationError("invalid API key", response=response, body=response.json())


def _mock_client(category: str) -> MagicMock:
    """Build a fake Groq client whose chat.completions.create() returns `category`."""
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(
        {"reasoning": "test reasoning", "category": category}
    )
    client.chat.completions.create.return_value = response
    return client


# One representative email per category, modelled on real records in
# sdoc-hackathon-bundle/inbox so the prompt assertions exercise realistic input.

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

SI_REQUEST_EMAIL = {
    "email_id": "email_test_003",
    "from": "ops@example-shipping.com",
    "subject": "REQUEST SI _ 5BBB-22334 _ GDANSK_POLAND _ NORDIC PAPER GMBH _ SIJ10518",
    "body": (
        "Hi Willy\n\nPlease find Shipping instruction for 5BBB-22334.\n\n"
        "POL: SINGAPORE\nPOD: GDANSK, POLAND\n\n"
        "Shipper:\nAPRIL FINE PAPER TRADING\n77 ROBINSON ROAD, #21-01\n"
        "SINGAPORE 068896\n\nConsignee:\nNORDIC PAPER GMBH\n\n"
        "Notify Party:\nSAME AS CONSIGNEE\n"
    ),
    "attachments": [],
}

INVOICE_QUERY_EMAIL = {
    "email_id": "email_test_004",
    "from": "finance@example-freight.com",
    "subject": "RE_ LOCAL CHARGES FOB - KARGOSMAR - 5CCC-61849 - TELEX RELEASE CHARGES",
    "body": (
        "Hi,\n\nQuery on invoice 5250075931: is the THC / local charge included "
        "or billed separately? Please advise the breakdown.\n\n"
        "Best Regards,\nShipping Documentation"
    ),
    "attachments": [],
}

GENERAL_EMAIL = {
    "email_id": "email_test_005",
    "from": "noreply@example-shipping.com",
    "subject": "15_01_2026 - UPDATE SUMMARY LE HAVRE V.QI540A",
    "body": (
        "Dear Team,\n\nPlease find attached the list of outstanding BL (BDP SG). "
        "Kindly action the pending items.\n\nRegards,\nDocumentation"
    ),
    "attachments": [],
}

EMAILS_BY_CATEGORY = {
    "BL_COMPARISON": BL_COMPARISON_EMAIL,
    "SI_REQUEST": SI_REQUEST_EMAIL,
    "INVOICE_QUERY": INVOICE_QUERY_EMAIL,
    "GENERAL": GENERAL_EMAIL,
    "SPAM": SPAM_EMAIL,
}


@pytest.mark.parametrize("expected_category", CATEGORIES)
def test_classify_email_returns_the_model_category(expected_category):
    email = EMAILS_BY_CATEGORY[expected_category]
    client = _mock_client(expected_category)

    result = classify_email(email, client=client)

    assert result == expected_category


def test_every_category_has_a_fixture():
    """Guards against a category being added to schema.py but left untested."""
    assert set(EMAILS_BY_CATEGORY) == set(CATEGORIES)


def test_the_system_prompt_documents_every_category():
    for category in CATEGORIES:
        assert category in SYSTEM_PROMPT


def test_classify_email_calls_the_api_with_the_expected_model_and_prompt():
    client = _mock_client("BL_COMPARISON")

    classify_email(BL_COMPARISON_EMAIL, client=client)

    client.chat.completions.create.assert_called_once()
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == MODEL  # always tracks classify.py's MODEL constant
    messages = kwargs["messages"]
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    user_content = messages[1]["content"]
    assert BL_COMPARISON_EMAIL["subject"] in user_content
    assert BL_COMPARISON_EMAIL["from"] in user_content
    assert "attachments/email_test_001_SI.txt" in user_content


def test_classify_email_lists_every_attachment_in_the_prompt():
    client = _mock_client("BL_COMPARISON")

    classify_email(BL_COMPARISON_EMAIL, client=client)

    _, kwargs = client.chat.completions.create.call_args
    user_content = kwargs["messages"][1]["content"]
    for attachment in BL_COMPARISON_EMAIL["attachments"]:
        assert attachment in user_content


def test_classify_email_marks_missing_attachments_as_none():
    client = _mock_client("SPAM")

    classify_email(SPAM_EMAIL, client=client)

    _, kwargs = client.chat.completions.create.call_args
    assert "Attachments: (none)" in kwargs["messages"][1]["content"]


def test_classify_email_requests_structured_json_output():
    """openai/gpt-oss-120b needs response_format set to a strict json_schema,
    or it may return prose instead of the JSON classify_email() expects to
    parse, or JSON shaped differently than _ClassificationOutput expects."""
    client = _mock_client("GENERAL")

    classify_email(GENERAL_EMAIL, client=client)

    _, kwargs = client.chat.completions.create.call_args
    response_format = kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert set(schema["required"]) == {"reasoning", "category"}
    assert set(schema["properties"]["category"]["enum"]) == set(CATEGORIES)


def test_classify_email_builds_a_default_client_when_none_is_given(monkeypatch):
    client = _mock_client("GENERAL")
    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("classify.Groq", lambda api_key: client)

    result = classify_email(GENERAL_EMAIL)

    assert result == "GENERAL"
    client.chat.completions.create.assert_called_once()


def test_reasoning_is_generated_before_the_category():
    """Chain-of-thought only helps if the model writes `reasoning` first - with
    the fields the other way round it would rationalise an answer it already
    committed to."""
    from classify import _ClassificationOutput

    assert list(_ClassificationOutput.model_fields) == ["reasoning", "category"]


def test_the_system_prompt_states_the_tie_breaking_order():
    assert "TIE-BREAKING" in SYSTEM_PROMPT


def test_classify_email_retries_on_server_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("classify.time.sleep", lambda _seconds: None)
    client = _mock_client("GENERAL")
    good_response = client.chat.completions.create.return_value
    client.chat.completions.create.side_effect = [
        _server_error(),
        _server_error(),
        good_response,
    ]

    result = classify_email(GENERAL_EMAIL, client=client)

    assert result == "GENERAL"
    assert client.chat.completions.create.call_count == 3


def test_classify_email_gives_up_after_max_attempts_on_server_error(monkeypatch):
    monkeypatch.setattr("classify.time.sleep", lambda _seconds: None)
    client = _mock_client("GENERAL")
    client.chat.completions.create.side_effect = _server_error()

    with pytest.raises(InternalServerError):
        classify_email(GENERAL_EMAIL, client=client)

    assert client.chat.completions.create.call_count == 3


def test_classify_email_does_not_retry_on_client_error(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("classify.time.sleep", lambda seconds: sleep_calls.append(seconds))
    client = _mock_client("GENERAL")
    client.chat.completions.create.side_effect = _client_error()

    with pytest.raises(AuthenticationError):
        classify_email(GENERAL_EMAIL, client=client)

    assert client.chat.completions.create.call_count == 1
    assert sleep_calls == []


@pytest.mark.live_api
@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="requires a real GROQ_API_KEY to call the live API",
)
def test_classify_email_live_api_classifies_a_real_bl_comparison_email():
    """Integration smoke test - hits the real Groq API. Costs a small amount
    and is skipped automatically unless GROQ_API_KEY is set."""
    result = classify_email(BL_COMPARISON_EMAIL)
    assert result == "BL_COMPARISON"
