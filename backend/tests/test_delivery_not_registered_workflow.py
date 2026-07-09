from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.agent_system import Issue, IssueAction
from app.models.base import Base
from app.models.source_systems import Country, Kit, Shipment, Site, Study
from app.services.gmail_toolkit_service import ReceivedReply, SentEmail
from app.services.gemini_service import GeminiEmailDraft, GeminiReplyDecision
from app.workflows import delivery_not_registered as delivery_workflow
from app.workflows import orchestrator


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
    sent_messages = []

    def fake_generate_email(*, issue_id, candidate, follow_up_count, receipt_instructions):
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

    monkeypatch.setattr(delivery_workflow, "generate_delivery_followup_email", fake_generate_email)
    monkeypatch.setattr(delivery_workflow, "classify_delivery_reply", fake_classify_reply)
    monkeypatch.setattr(delivery_workflow, "send_email", fake_send_email)
    monkeypatch.setattr(orchestrator, "send_email", fake_send_email)
    return sent_messages


def seed_unregistered_delivery(db):
    db.add(
        Study(
            study_id="STUDY-1",
            study_status="ACTIVE",
            study_manager_name="Study Manager",
            study_manager_email="study@example.com",
            supply_manager_name="Supply Manager",
            supply_manager_email="supply@example.com",
        )
    )
    db.add(
        Country(
            study_id="STUDY-1",
            country_id="US",
            country_name="United States",
        )
    )
    db.add(
        Site(
            study_id="STUDY-1",
            site_id="SITE-1",
            country_id="US",
            site_status="ACTIVE",
            investigator_name="Site Investigator",
            investigator_email="site@example.com",
        )
    )
    db.add(
        Shipment(
            study_id="STUDY-1",
            shipment_id="SHIP-1",
            site_id="SITE-1",
            logistics_status="DELIVERED",
            delivered_at=datetime.utcnow() - timedelta(days=1),
            carrier_name="Mock Carrier",
            tracking_number="TRACK-1",
            product_label="DRUG-A",
        )
    )
    db.add(
        Kit(
            study_id="STUDY-1",
            kit_id="KIT-1",
            shipment_id="SHIP-1",
            site_id="SITE-1",
            kit_status="PENDING_RECEIPT",
            product_label="DRUG-A",
        )
    )
    db.commit()


def make_reply(issue_id, outbound_message_id, body, uid="101"):
    return ReceivedReply(
        uid=uid,
        message_id=f"<reply-{uid}@test>",
        in_reply_to=outbound_message_id,
        references=(outbound_message_id,),
        issue_id_from_subject=None,
        sender="rudymer313@gmail.com",
        recipient="rudrank2004@gmail.com",
        subject="Re: Receipt confirmation needed for shipment SHIP-1",
        body=body,
        gmail_thread_id=f"thread-{issue_id}",
        gmail_message_id=f"gmail-reply-{uid}",
    )


def test_scan_uses_main_risk_initial_and_follow_up_nodes(db, mock_email):
    seed_unregistered_delivery(db)

    result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = result["payload"]["issue_id"]
    nodes = [item["node"] for item in result["events"]]

    assert result["status"] == "open"
    assert nodes == [
        "Main Node",
        "Supply/Logistics Node",
        "Initial Node",
        "Follow-up Node",
        "Follow-up Node",
    ]
    assert mock_email[0]["sent"].sender == "rudrank2004@gmail.com"
    assert mock_email[0]["sent"].recipient == "rudymer313@gmail.com"
    assert "CTA-ISSUE" not in mock_email[0]["sent"].subject
    assert "issue" not in mock_email[0]["sent"].subject.lower()
    assert "Shipment ID: SHIP-1" in mock_email[0]["body"]
    assert db.get(Issue, issue_id).follow_up_count == 1


def test_repeated_scan_does_not_send_duplicate_email_while_waiting(
    db,
    mock_email,
):
    seed_unregistered_delivery(db)
    orchestrator.run_full_agentic_workflow(db)

    repeated = orchestrator.run_full_agentic_workflow(db)[0]

    assert repeated["status"] == "open"
    assert len(mock_email) == 1
    assert db.query(Issue).one().follow_up_count == 1


def test_fixed_email_returns_to_initial_and_closes_after_irt_update(
    db,
    mock_email,
    monkeypatch,
):
    seed_unregistered_delivery(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]
    outbound_id = mock_email[0]["sent"].message_id

    kit = db.get(Kit, ("STUDY-1", "KIT-1"))
    kit.kit_status = "RECEIVED"
    db.commit()

    reply = make_reply(
        issue_id,
        outbound_id,
        "The issue is fixed and the receipt is registered in IRT.",
    )
    monkeypatch.setattr(orchestrator, "fetch_unread_replies", lambda: [reply])
    monkeypatch.setattr(
        orchestrator,
        "complete_reply_processing",
        lambda received: None,
    )

    result = orchestrator.process_email_replies(db)[0]
    nodes = [item["node"] for item in result["events"]]

    assert result["status"] == "closed"
    assert nodes == ["Decision Node", "Initial Node", "Closing Node"]
    assert db.get(Issue, issue_id).status == "Closed"
    assert db.get(Issue, issue_id).response_count == 1


def test_no_knowledge_email_goes_from_decision_to_escalation(
    db,
    mock_email,
    monkeypatch,
):
    seed_unregistered_delivery(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]
    reply = make_reply(
        issue_id,
        mock_email[0]["sent"].message_id,
        "I have no knowledge of this shipment and cannot find it.",
    )
    monkeypatch.setattr(orchestrator, "fetch_unread_replies", lambda: [reply])
    monkeypatch.setattr(
        orchestrator,
        "complete_reply_processing",
        lambda received: None,
    )

    result = orchestrator.process_email_replies(db)[0]

    assert result["status"] == "escalated"
    assert [item["node"] for item in result["events"]] == [
        "Decision Node",
        "Closing Node",
    ]
    assert db.get(Issue, issue_id).status == "Escalated"
    assert "CTA-ISSUE" not in mock_email[-1]["sent"].subject
    assert mock_email[-1]["sent"].subject.startswith("Human review needed")


def test_overdue_check_in_resends_follow_up_then_escalates(db, mock_email):
    seed_unregistered_delivery(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]

    def make_reminder_due(**filters):
        reminder = (
            db.query(IssueAction)
            .filter_by(issue_id=issue_id, action_type="RECEIPT_REMINDER", **filters)
            .order_by(IssueAction.action_id.desc())
            .first()
        )
        reminder.due_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

    make_reminder_due(status="Sent")
    second = orchestrator.process_due_issue_checks(db)[0]

    assert second["status"] == "open"
    assert [item["node"] for item in second["events"]] == [
        "Initial Node",
        "Follow-up Node",
        "Follow-up Node",
    ]
    assert db.get(Issue, issue_id).follow_up_count == 2
    assert len(mock_email) == 2

    make_reminder_due(status="Sent")
    third = orchestrator.process_due_issue_checks(db)[0]

    assert third["status"] == "escalated"
    assert [item["node"] for item in third["events"]] == [
        "Initial Node",
        "Follow-up Node",
        "Closing Node",
    ]
    assert db.get(Issue, issue_id).status == "Escalated"
    assert db.get(Issue, issue_id).follow_up_count == 2


def test_mark_kits_received_closes_issue_without_a_reply(db, mock_email):
    seed_unregistered_delivery(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]

    result = orchestrator.resolve_delivery_issue(db, issue_id)

    assert result["status"] == "closed"
    issue = db.get(Issue, issue_id)
    assert issue.status == "Closed"
    kit = db.get(Kit, ("STUDY-1", "KIT-1"))
    assert kit.kit_status == "RECEIVED"


def test_fixed_but_still_pending_repeats_once_then_escalates(
    db,
    mock_email,
):
    seed_unregistered_delivery(db)
    first = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first["payload"]["issue_id"]

    second = orchestrator.continue_issue(
        db,
        issue_id=issue_id,
        entrypoint="email_response",
        response_text="I fixed the receipt.",
    )
    assert second["status"] == "open"
    assert db.get(Issue, issue_id).follow_up_count == 2

    third = orchestrator.continue_issue(
        db,
        issue_id=issue_id,
        entrypoint="email_response",
        response_text="It is definitely fixed now.",
    )
    assert third["status"] == "escalated"
    assert db.get(Issue, issue_id).follow_up_count == 2


def test_worker_sends_legacy_queued_follow_up_actions(db, mock_email):
    seed_unregistered_delivery(db)
    first = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first["payload"]["issue_id"]

    legacy_action = IssueAction(
        issue_id=issue_id,
        action_type="RECEIPT_REMINDER",
        status="Queued",
        recipient="rudymer313@gmail.com",
        subject="Legacy queued reminder",
        message="Please complete the receipt.",
    )
    db.add(legacy_action)
    db.commit()

    processed = orchestrator.process_pending_outbound_emails(db)

    assert processed[-1]["status"] == "Sent"
    assert db.get(IssueAction, legacy_action.action_id).status == "Sent"
    assert len(mock_email) == 2


def test_mark_kits_received_resolves_the_whole_shipment_at_once(db, mock_email):
    seed_unregistered_delivery(db)
    db.add(
        Kit(
            study_id="STUDY-1",
            kit_id="KIT-2",
            shipment_id="SHIP-1",
            site_id="SITE-1",
            kit_status="PENDING_RECEIPT",
            product_label="DRUG-A",
        )
    )
    db.commit()

    first = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first["payload"]["issue_id"]

    result = orchestrator.resolve_delivery_issue(db, issue_id)

    assert result["status"] == "closed"
    assert db.get(Issue, issue_id).status == "Closed"
    assert db.get(Kit, ("STUDY-1", "KIT-1")).kit_status == "RECEIVED"
    assert db.get(Kit, ("STUDY-1", "KIT-2")).kit_status == "RECEIVED"


def test_scoped_detection_only_processes_matching_study(db, mock_email):
    seed_unregistered_delivery(db)
    db.add(Study(study_id="STUDY-2", study_status="ACTIVE"))
    db.add(Country(study_id="STUDY-2", country_id="US", country_name="United States"))
    db.add(Site(study_id="STUDY-2", site_id="SITE-2", country_id="US", site_status="ACTIVE"))
    db.add(
        Shipment(
            study_id="STUDY-2",
            shipment_id="SHIP-2",
            site_id="SITE-2",
            logistics_status="DELIVERED",
            delivered_at=datetime.utcnow() - timedelta(days=1),
            carrier_name="Mock Carrier 2",
            tracking_number="TRACK-2",
            product_label="DRUG-B",
        )
    )
    db.add(
        Kit(
            study_id="STUDY-2",
            kit_id="KIT-3",
            shipment_id="SHIP-2",
            site_id="SITE-2",
            kit_status="PENDING_RECEIPT",
            product_label="DRUG-B",
        )
    )
    db.commit()

    results = orchestrator.run_full_agentic_workflow(db, study_id="STUDY-1")

    assert len(results) == 1
    issues = db.query(Issue).all()
    assert len(issues) == 1
    assert issues[0].reference_key.split(":")[1] == "STUDY-1"


def test_update_shipment_status_correction_closes_issue(db, mock_email):
    seed_unregistered_delivery(db)
    first = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first["payload"]["issue_id"]

    result = orchestrator.update_delivery_shipment(db, issue_id, {"logistics_status": "IN_TRANSIT"})

    assert result["status"] == "closed"
    assert db.get(Issue, issue_id).status == "Closed"
    shipment = db.get(Shipment, ("STUDY-1", "SHIP-1"))
    assert shipment.logistics_status == "IN_TRANSIT"
