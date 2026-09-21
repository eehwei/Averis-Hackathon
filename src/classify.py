"""Classifies inbox emails into one of five categories using the Claude API."""

from __future__ import annotations

from typing import Any, Optional

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        pass

from schema import Email, EmailCategory

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an email triage assistant for a shipping documentation \
team at a paper trading company. Classify each incoming email into exactly one \
of these categories:

- BL_COMPARISON: sender is sending, or asking to confirm, both a Shipping \
Instruction (SI) and a draft Bill of Lading (BL) so the two can be checked \
against each other. Usually has SI and BL attachments, or the body asks to \
"check the details and confirm" a draft BL.
- SI_REQUEST: sender is sending or requesting the Shipping Instruction itself \
(shipper / consignee / notify party / port / cargo details) and is not asking \
for a BL comparison.
- INVOICE_QUERY: sender is asking about freight, charges, invoices, D&D / \
detention fees, or billing discrepancies.
- GENERAL: internal operational emails not covered above - status updates, \
reminders, berthing reports, outstanding-item lists, HR notices, etc.
- SPAM: unsolicited, phishing, or promotional emails unrelated to a real \
shipment.

Examples:

Example 1
From: docs@example-trading.com
Subject: TO CONFIRM DOCS _ 5AAA-00111 _ ROTTERDAM_NETHERLANDS _ ACME TRADING BV
Attachments: attachments/email_x_SI.txt, attachments/email_x_BL.txt
Body: Hi team, Attached are the SI and draft BL for OC 5AAA-00111. Please check \
the details and confirm.
-> BL_COMPARISON

Example 2
From: ops@example-shipping.com
Subject: REQUEST SI _ 5BBB-22334 _ HAMBURG_GERMANY _ NORDIC PAPER GMBH
Attachments: (none)
Body: Please find Shipping instruction for 5BBB-22334. POL: SINGAPORE POD: \
HAMBURG, GERMANY. Shipper: ... Consignee: ... Notify Party: ...
-> SI_REQUEST

Example 3
From: finance@example-freight.com
Subject: Total Freight - CHINA - 5CCC-99887
Attachments: (none)
Body: Query on invoice 5250099887: is the THC / local charge included or \
billed separately? Please advise the breakdown.
-> INVOICE_QUERY

Example 4
From: noreply@example-shipping.com
Subject: 15_02_2026 - UPDATE SUMMARY SHANGHAI V.AB123C
Attachments: (none)
Body: Dear Team, Please find attached the list of outstanding BL. Kindly \
action the pending items. Regards, Documentation
-> GENERAL

Example 5
From: info@crypto-invest.net
Subject: Increase your shipping revenue with this ONE weird trick
Attachments: (none)
Body: Dear user, your mailbox has exceeded its storage limit. Verify your \
account within 24 hours to avoid deactivation: http://webmail-verify.co
-> SPAM

Respond with only the category."""


class _ClassificationOutput(BaseModel):
    category: EmailCategory


def _format_email(email: Email) -> str:
    attachments = "\n".join(email.get("attachments") or []) or "(none)"
    return (
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n"
        f"Attachments: {attachments}\n\n"
        f"Body:\n{email['body']}"
    )


def classify_email(
    email: Email, *, client: Optional[Any] = None
) -> EmailCategory:
    """Classify an email into one of the categories in schema.EmailCategory."""
    if anthropic is None or BaseModel.__module__ == __name__:
        raise RuntimeError("LLM classification requires anthropic and pydantic")
    client = client or anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _format_email(email)}],
        output_format=_ClassificationOutput,
    )

    return response.parsed_output.category
