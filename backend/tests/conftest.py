import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.services.gemini_service import GeminiEmailDraft, GeminiReplyDecision
from app.services.gmail_toolkit_service import SentEmail
from app.workflows import delivery_not_registered as delivery_workflow
from app.workflows import orchestrator
from app.workflows import shipment_delays as delay_workflow


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def mock_email(monkeypatch):
    """Shared across every workflow test file: mocks Gemini drafting/classification
    and the Gmail send, for both Delivery Not Registered and Shipment Delays.

    Note: both issue types' follow-up/closing nodes send through the same
    `send_and_record` helper (defined in delivery_not_registered.py), which
    resolves `send_email` from that module's own globals regardless of which
    issue type called it — so patching `delivery_workflow.send_email` alone
    covers sending for both issue types. Only email *drafting* is per-module.
    """
    sent_messages = []

    def fake_generate_delivery_email(*, issue_id, candidate, follow_up_count, receipt_instructions):
        return GeminiEmailDraft(
            subject=f"IRT receipt required for shipment {candidate['shipment_id']}",
            body=(
                "A Gemini-generated receipt reminder.\n\n"
                f"Issue ID: {issue_id}\n"
                f"Shipment ID: {candidate['shipment_id']}\n"
                f"Study ID: {candidate['study_id']}\n"
                f"Site ID: {candidate['site_id']}\n"
                f"Pending kit count: {candidate['pending_kit_count']}\n"
                f"Instructions: {receipt_instructions}"
            ),
            model_used="mock-gemini",
            prompt_name="mock.follow_up",
        )

    def fake_generate_delay_email(*, issue_id, candidate, follow_up_count):
        return GeminiEmailDraft(
            subject=f"Status update needed for shipment {candidate['shipment_id']}",
            body=(
                "A Gemini-generated delay status request.\n\n"
                f"Issue ID: {issue_id}\n"
                f"Shipment ID: {candidate['shipment_id']}\n"
                f"Study ID: {candidate['study_id']}\n"
                f"Site ID: {candidate['site_id']}\n"
                f"Days in transit: {candidate['days_in_transit']}"
            ),
            model_used="mock-gemini",
            prompt_name="mock.delay_follow_up",
        )

    def fake_classify_reply(response_text, *, issue_id=None, candidate=None):
        text = response_text.lower()
        if "no knowledge" in text or "cannot find" in text:
            outcome = "no_knowledge"
        elif "fixed" in text or "registered" in text or "resolved" in text:
            outcome = "fixed"
        else:
            outcome = "unclear"
        return GeminiReplyDecision(
            outcome=outcome,
            confidence=0.99,
            rationale="mock classifier",
            model_used="mock-gemini",
            prompt_name="mock.decision",
        )

    def fake_send_email(*, issue_id, subject, body, reply_to_message_id=None):
        sent = SentEmail(
            message_id=f"<message-{len(sent_messages) + 1}@test>",
            sender="rudrank2004@gmail.com",
            recipient="rudymer313@gmail.com",
            subject=subject,
            gmail_thread_id=f"thread-{issue_id}",
            raw_tool_result="mock GmailToolkit send result",
        )
        sent_messages.append(
            {
                "sent": sent,
                "body": body,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return sent

    monkeypatch.setattr(delivery_workflow, "generate_delivery_followup_email", fake_generate_delivery_email)
    monkeypatch.setattr(delivery_workflow, "classify_delivery_reply", fake_classify_reply)
    monkeypatch.setattr(delivery_workflow, "send_email", fake_send_email)
    monkeypatch.setattr(delay_workflow, "generate_shipment_delay_email", fake_generate_delay_email)
    monkeypatch.setattr(orchestrator, "send_email", fake_send_email)
    return sent_messages
