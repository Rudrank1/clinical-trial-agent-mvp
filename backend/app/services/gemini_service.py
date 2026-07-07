from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

load_dotenv()

DecisionOutcome = Literal["fixed", "no_knowledge", "unclear"]


class DeliveryFollowUpEmail(BaseModel):
    subject: str = Field(
        description="Natural email subject. Must not include internal issue IDs or workflow tokens."
    )
    body: str = Field(description="Natural plain-text email body to send to the site manager.")


class DeliveryReplyInterpretation(BaseModel):
    outcome: DecisionOutcome = Field(
        description="fixed, no_knowledge, or unclear according to the delivery workflow rules."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence from 0 to 1.")
    rationale: str = Field(description="Brief reason for the classification.")


@dataclass(frozen=True)
class GeminiEmailDraft:
    subject: str
    body: str
    model_used: str
    prompt_name: str


@dataclass(frozen=True)
class GeminiReplyDecision:
    outcome: DecisionOutcome
    confidence: float
    rationale: str
    model_used: str
    prompt_name: str


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _llm(temperature: float = 0.2):
    return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=temperature)


def generate_delivery_followup_email(
    *,
    issue_id: int,
    candidate: dict[str, Any],
    follow_up_count: int,
    receipt_instructions: str,
) -> GeminiEmailDraft:
    """Use Gemini to write the issue-specific follow-up email."""
    llm = _llm(temperature=0.45)
    prompt_name = "delivery_not_registered.follow_up_email.v2_natural"
    payload = _candidate_payload(candidate)
    prompt = f"""
You are a clinical trial supply coordinator writing a real email to a site manager.

Write a natural, human-sounding follow-up email about a shipment receipt mismatch.
The email should feel like it came from an operations teammate, not from an automated ticketing system.

Context:
- The carrier's tracking data indicates the shipment was delivered.
- The receipt step for this shipment still hasn't been marked complete.
- The site manager needs to confirm and complete the receipt.

Style requirements:
- Use a practical subject line that would make sense to the recipient without internal database context.
- Do NOT mention CTA-ISSUE, issue ID, database ID, workflow node, agent, automation, Gemini, AI, JSON, or prompt in the subject or body.
- Do NOT name or assume any specific software system (no IRT, IBP, CTMS, SAP, or similar internal system names) — the recipient's organization may not use the same tools. Refer to actions and records in plain, generic terms instead (e.g. "the receipt," "your tracking system," "your records").
- Do NOT include a tracking token in the subject or body.
- Do NOT sound like a generated autoresponse.
- Keep the tone polite, calm, plain, and direct — avoid technical or clinical-operations jargon.
- Start with a normal greeting.
- Include a short reason for the note.
- Include the important details in a readable plain-text format.
- Do NOT ask the recipient to reply to this email — just ask them to complete the receipt. The update will be picked up automatically once it's done.
- Close with a normal sign-off from the Clinical Supply Monitoring Team.
- Do not invent facts that are not in the supplied JSON.
- Use short paragraphs with blank lines between them.
- When explaining multiple items, use bullets.
- Do NOT return one dense paragraph.
- PLEASE use line breaks and whitespace after greeting and before sign off.
- This is follow-up attempt {follow_up_count}; if this is not the first attempt, politely acknowledge that this is a follow-up, but do not make it sound accusatory.
- Return only the structured email object.

Required details to include when available:
- Shipment ID
- Study ID
- Site ID
- Delivery timestamp
- Carrier and tracking number
- Product label
- Pending kit count
- Receipt instructions

Receipt instructions:
{receipt_instructions}

Issue data JSON:
{json.dumps(payload, indent=2, default=str)}
""".strip()

    structured = llm.with_structured_output(DeliveryFollowUpEmail)
    result = structured.invoke(prompt)
    return GeminiEmailDraft(
        subject=_natural_subject(str(result.subject), candidate),
        body=_natural_body(str(result.body)),
        model_used=GEMINI_MODEL,
        prompt_name=prompt_name,
    )


def interpret_delivery_reply(
    *,
    issue_id: int,
    reply_text: str,
    candidate: dict[str, Any],
) -> GeminiReplyDecision:
    """Use Gemini to interpret the inbound site response for the Decision Node."""
    llm = _llm(temperature=0.0)
    prompt_name = "delivery_not_registered.decision_node.v1"

    prompt = f"""
You are the Decision Node for a Delivery Not Registered clinical-trial workflow.

Classify the site manager's reply into exactly one outcome:
- fixed: the reply clearly claims the shipment receipt was completed, registered, fixed, or corrected.
- no_knowledge: the reply claims the site has no knowledge of the shipment, cannot find the shipment, did not receive it, or rejects ownership.
- unclear: the reply is ambiguous, incomplete, asks a question without accepting ownership, says someone else may own it, or does not clearly claim fixed/no_knowledge.

Workflow routing:
- fixed returns to Initial Node for source-system verification.
- no_knowledge routes to Closing Node for escalation.
- unclear routes to Closing Node for escalation.

Do not classify as fixed just because the sender is polite or says they will check later.
Return only the structured classification object.

Issue ID: {issue_id}
Issue data JSON:
{json.dumps(_candidate_payload(candidate), indent=2, default=str)}

Reply text:
{reply_text}
""".strip()

    structured = llm.with_structured_output(DeliveryReplyInterpretation)
    result = structured.invoke(prompt)
    outcome = str(result.outcome).strip().lower()
    if outcome not in {"fixed", "no_knowledge", "unclear"}:
        outcome = "unclear"
    return GeminiReplyDecision(
        outcome=outcome,  # type: ignore[arg-type]
        confidence=float(result.confidence),
        rationale=str(result.rationale).strip(),
        model_used=GEMINI_MODEL,
        prompt_name=prompt_name,
    )


def _candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "reference_key",
        "shipment_id",
        "study_id",
        "site_id",
        "country",
        "depot",
        "expected_delivery_date",
        "delivered_at",
        "sap_status",
        "carrier_name",
        "tracking_number",
        "carrier_proof_of_delivery",
        "product_label",
        "pending_kit_count",
        "pending_kit_ids",
        "available_kit_count",
        "upcoming_drug_visit_count",
        "severity",
    ]
    return {key: candidate.get(key) for key in keys}


def _natural_subject(subject: str, candidate: dict[str, Any]) -> str:
    """Remove internal workflow language from Gemini output and keep the subject useful."""
    clean = str(subject or "").strip()
    clean = re.sub(r"\[?CTA[-_ ]?ISSUE[-_ ]?\d*\]?", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bissue\s*#?\d+\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bworkflow\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip(" -:|")
    if not clean:
        shipment_id = candidate.get("shipment_id") or "the recent shipment"
        clean = f"Receipt confirmation needed for shipment {shipment_id}"
    return clean[:180]


def _natural_body(body: str) -> str:
    """Keep the email plain-text and remove accidental internal identifiers."""
    clean = str(body or "").strip()
    clean = re.sub(r"CTA[-_ ]?ISSUE[-_ ]?\d+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bIssue ID:\s*\d+\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bworkflow node\b", "process step", clean, flags=re.IGNORECASE)
    clean = clean.replace("```", "").strip()
    return clean
