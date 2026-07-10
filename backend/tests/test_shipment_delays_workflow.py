from datetime import datetime, timedelta

from app.models.agent_system import Issue, IssueAction
from app.models.source_systems import Country, Shipment, Site, Study
from app.workflows import orchestrator


def seed_delayed_shipment(db):
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
            logistics_status="DELAYED",
            requested_at=datetime.utcnow() - timedelta(days=10),
            shipped_at=datetime.utcnow() - timedelta(days=8),
            carrier_name="Mock Carrier",
            tracking_number="TRACK-1",
            product_label="DRUG-A",
        )
    )
    db.commit()


def test_scan_creates_shipment_delays_issue_and_sends_status_request(db, mock_email):
    seed_delayed_shipment(db)

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
    issue = db.get(Issue, issue_id)
    assert issue.issue_type == "Shipment Delays"
    assert issue.follow_up_count == 1
    assert "CTA-ISSUE" not in mock_email[0]["sent"].subject
    assert "issue" not in mock_email[0]["sent"].subject.lower()


def test_repeated_scan_does_not_send_duplicate_email_while_waiting(db, mock_email):
    seed_delayed_shipment(db)
    orchestrator.run_full_agentic_workflow(db)

    repeated = orchestrator.run_full_agentic_workflow(db)[0]

    assert repeated["status"] == "open"
    assert len(mock_email) == 1
    assert db.query(Issue).one().follow_up_count == 1


def test_overdue_check_in_resends_follow_up_then_escalates(db, mock_email):
    seed_delayed_shipment(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]

    def make_reminder_due():
        reminder = (
            db.query(IssueAction)
            .filter_by(issue_id=issue_id, action_type="DELAY_STATUS_REQUEST", status="Sent")
            .order_by(IssueAction.action_id.desc())
            .first()
        )
        reminder.due_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

    make_reminder_due()
    second = orchestrator.process_due_issue_checks(db)[0]

    assert second["status"] == "open"
    assert db.get(Issue, issue_id).follow_up_count == 2
    assert len(mock_email) == 2

    make_reminder_due()
    third = orchestrator.process_due_issue_checks(db)[0]

    assert third["status"] == "escalated"
    assert db.get(Issue, issue_id).status == "Escalated"
    assert db.get(Issue, issue_id).follow_up_count == 2
    assert mock_email[-1]["sent"].subject.startswith("Human review needed")


def test_shipment_recovering_closes_the_issue_on_recheck(db, mock_email):
    seed_delayed_shipment(db)
    first_result = orchestrator.run_full_agentic_workflow(db)[0]
    issue_id = first_result["payload"]["issue_id"]

    shipment = db.get(Shipment, ("STUDY-1", "SHIP-1"))
    shipment.logistics_status = "IN_TRANSIT"
    db.commit()

    result = orchestrator.continue_issue(db, issue_id=issue_id, entrypoint="verify")

    assert result["status"] == "closed"
    assert db.get(Issue, issue_id).status == "Closed"
