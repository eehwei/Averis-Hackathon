
"""Classifies inbox emails into one of five categories using the Groq API."""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from dotenv import load_dotenv
from groq import Groq, InternalServerError
from pydantic import BaseModel

from schema import CATEGORIES, Email, EmailCategory

load_dotenv()

# openai/gpt-oss-120b: the largest general-purpose model this account's Groq
# free tier has active (checked live via client.models.list() - Groq's
# lineup and per-account access change over time, so this is not a fixed
# assumption). It supports strict JSON-schema structured output and its
# 1,000 requests/day quota covers a ~520-email run with headroom to spare.
MODEL = "openai/gpt-oss-120b"

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "email_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "category": {"type": "string", "enum": list(CATEGORIES)},
            },
            "required": ["reasoning", "category"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = """You are an email triage assistant for a shipping documentation \
team at a paper trading company. Classify each incoming email into exactly one \
of these categories:

- BL_COMPARISON: the email is about checking a draft Bill of Lading (BL) against \
the Shipping Instruction (SI). This covers both cases: the SI and draft BL are \
attached for checking, AND the sender is asking for a draft BL to be sent so it \
can be checked. Attachments are not required.
- SI_REQUEST: sender is sending or requesting the Shipping Instruction itself \
(shipper / consignee / notify party / port / cargo details) and is not asking \
for a BL comparison.
- INVOICE_QUERY: sender is asking about freight, charges, invoices, D&D / \
detention fees, or billing discrepancies.
- GENERAL: internal operational emails not covered above - status updates, \
reminders, berthing reports, outstanding-item lists, HR notices.
- SPAM: unsolicited, phishing, or promotional emails unrelated to a real \
shipment.

TIE-BREAKING. Many emails partly fit two categories. When that happens, apply \
the FIRST rule below that matches and ignore the rest:

1. SPAM beats everything. Phishing, credential harvesting, bank-detail changes \
and unsolicited promotion stay SPAM even when they imitate a real invoice, \
shipment or BL request.
2. BL_COMPARISON when getting a draft BL checked is the POINT of the email \
- either the SI and draft BL are attached for checking, or the sender asks \
for a draft BL to be sent so it can be checked. "Check", "confirm", "verify" \
and "compare" all count as the same ask - "kindly confirm the BL is in order" \
and "compare the SI and draft BL and confirm" are both BL_COMPARISON. But what \
is being confirmed must be the BL or the shipping documents: "kindly confirm \
the amount before we release payment" is rule 4, and "confirm payment within \
24 hours" in an unsolicited email is rule 1. Attachments are NOT \
required: "please assist to send the draft BL for checking" is BL_COMPARISON \
with nothing attached. A later stage marks those NEEDS_REVIEW / \
missing_attachment - that is the correct outcome, not a reason to put them \
somewhere else.
   CARVE-OUT: if the body IS the Shipping Instruction itself - it lists \
shipper, consignee, notify party, POL/POD and cargo - then a closing line \
like "please revert with draft BL once available" is just the next step in \
the handover, NOT a request to check a BL. That email is SI_REQUEST. Only \
treat it as BL_COMPARISON if it actually asks for a BL to be checked, \
verified or compared.
3. SI_REQUEST if the email sends or asks for the Shipping Instruction \
itself, including when it closes by asking for the draft BL to follow.
4. INVOICE_QUERY if the email is mainly about money - freight, charges, \
invoices, billing.
5. GENERAL is the fallback for everything else operational - status updates, \
reminders, berthing reports, outstanding-item lists, HR notices.

Decide from what the sender is actually asking for in the body. Subject-line \
templates are reused across categories, so the subject alone never settles it.

Think briefly before answering: note what the sender actually wants, what is \
attached, and which tie-breaking rule decides it. Two or three sentences is \
enough. Put that in the `reasoning` field, then the label in `category`.

Examples:

Example 1
From: docs@example-trading.com
Subject: TO CONFIRM DOCS _ 5AAA-00111 _ ROTTERDAM_NETHERLANDS _ ACME TRADING BV
Attachments: attachments/email_x_SI.txt, attachments/email_x_BL.txt
Body: Hi team, Attached are the SI and draft BL for OC 5AAA-00111. Please check \
the details and confirm.
Reasoning: Both the SI and the draft BL are attached and the sender asks for \
them to be checked against each other. Rule 2 applies.
-> BL_COMPARISON

Example 2
From: ops@example-shipping.com
Subject: REQUEST SI _ 5BBB-22334 _ HAMBURG_GERMANY _ NORDIC PAPER GMBH
Attachments: (none)
Body: Please find Shipping instruction for 5BBB-22334. POL: SINGAPORE POD: \
HAMBURG, GERMANY. Shipper: ... Consignee: ... Notify Party: ...
Reasoning: The body is the Shipping Instruction itself and nothing is said \
about checking a BL. Rule 3 applies.
-> SI_REQUEST

Example 3
From: finance@example-freight.com
Subject: Total Freight - CHINA - 5CCC-99887
Attachments: (none)
Body: Query on invoice 5250099887: is the THC / local charge included or \
billed separately? Please advise the breakdown.
Reasoning: The email is purely a billing question about an invoice. Rule 4 \
applies.
-> INVOICE_QUERY

Example 4
From: noreply@example-shipping.com
Subject: 15_02_2026 - UPDATE SUMMARY SHANGHAI V.AB123C
Attachments: (none)
Body: Dear Team, Please find attached the list of outstanding BL. Kindly \
action the pending items. Regards, Documentation
Reasoning: An operational status summary listing outstanding items, with no \
specific BL to check. Rule 5 applies.
-> GENERAL

Example 5
From: docs@example-trading.com
Subject: RE_ TO CONFIRM DOCS _ 5DDD-03056 _ AQABA_JORDAN _ ROXCEL TRADING GMBH
Attachments: (none)
Body: Dear Hari, Please assist to send the draft BL for SIN832764835 for \
checking asap. Thank you.
Reasoning: The sender wants a draft BL sent so it can be checked, which is a BL \
check even though nothing is attached yet. Rule 2 applies regardless of \
attachments.
-> BL_COMPARISON

Example 6
From: ops@example-shipping.com
Subject: RE_ SI - EGLV054851017490 - DIRECT(EVER) - 5EEE-89354 - KLAIPEDA
Attachments: (none)
Body: Hi Teo, Please find Shipping instruction for 5EEE-89354. POL: NANTONG, \
CHINA POD: KLAIPEDA, LITHUANIA. Shipper: ... Consignee: ... Notify Party: \
... Description of Goods: 10X40'HC PAPERBOARD. Documents Required: 3 \
Original BL + 3 N/N. Please revert with draft BL once available.
Reasoning: The body is the Shipping Instruction itself. The closing line \
asks for a draft BL to follow, but does not ask for one to be checked, so \
the rule 2 carve-out sends this to rule 3.
-> SI_REQUEST

Example 7
From: info@crypto-invest.net
Subject: Increase your shipping revenue with this ONE weird trick
Attachments: (none)
Body: Dear user, your mailbox has exceeded its storage limit. Verify your \
account within 24 hours to avoid deactivation: http://webmail-verify.co
Reasoning: Unsolicited phishing aimed at harvesting credentials, unrelated to \
any real shipment. Rule 1 applies.
-> SPAM"""


class _ClassificationOutput(BaseModel):
    """Structured result of one classification.

    Field order matters: `reasoning` is declared first so the model writes it
    before committing to `category`. Reversing these two would still parse, but
    the reasoning would be written after the answer and could not inform it.
    """

    reasoning: str
    category: EmailCategory


def _format_email(email: Email) -> str:
    attachments = "\n".join(email.get("attachments") or []) or "(none)"
    return (
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n"
        f"Attachments: {attachments}\n\n"
        f"Body:\n{email['body']}"
    )


def classify_email(email: Email, *, client: Optional[Groq] = None) -> EmailCategory:
    """Classify an email into one of the categories in schema.EmailCategory."""
    client = client or Groq(api_key=os.environ["GROQ_API_KEY"])

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _format_email(email)},
    ]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format=_RESPONSE_FORMAT,
            )
            break
        except InternalServerError:
            # InternalServerError (5xx, e.g. 503) is transient - retry. A
            # 4xx error (e.g. AuthenticationError from an invalid API key)
            # will not succeed on retry, so it is left to propagate
            # immediately.
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_DELAY_SECONDS)

    result = _ClassificationOutput(**json.loads(response.choices[0].message.content))
    return result.category
