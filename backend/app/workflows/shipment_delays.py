from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.models.agent_system import Issue, IssueAction, IssueEvidence
from app.models.source_systems import Country, Shipment, Site, Study
from app.services.gemini_service import generate_shipment_delay_email
from app.workflows.delivery_not_registered import (
    FOLLOW_UP_INTERVAL_SECONDS,
    MAX_FOLLOW_UP_VISITS,
    is_check_in_due,
    route_after_follow_up,
    route_after_initial,
    send_and_record,
)
from app.workflows.risk_nodes import count_available_kits, count_upcoming_drug_visits
from app.workflows.state import AgentWorkflowState, event

ISSUE_TYPE = "Shipment Delays"
RISK_TYPE = "Supply/Logistics"
UPCOMING_VISIT_WINDOW_DAYS = 14
ESCALATION_REASONS = {
    "Follow-up Node": "We followed up more than once, but the shipment still hasn't started moving again or arrived.",
}

# Re-exported so orchestrator.py can wire this issue type's Initial/Follow-up
# Node edges with the same shared routers Delivery Not Registered uses.
__all__ = [
    "ISSUE_TYPE",
    "find_shipment_delay_candidates",
    "shipment_delay_initial_node",
    "shipment_delay_follow_up_node",
    "shipment_delay_closing_node",
    "route_after_initial",
    "route_after_follow_up",
    "get_delay_context_snapshot",
]


def find_shipment_delay_candidates(
    db,
    *,
    study_id: str | None = None,
    country_id: str | None = None,
    site_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(Shipment, Site, Country, Study)
        .join(
            Site,
            (Site.study_id == Shipment.study_id) & (Site.site_id == Shipment.site_id),
            isouter=True,
        )
        .join(
            Country,
            (Country.study_id == Site.study_id) & (Country.country_id == Site.country_id),
            isouter=True,
        )
        .join(Study, Study.study_id == Shipment.study_id, isouter=True)
        .where(Shipment.logistics_status == "DELAYED")
        .distinct()
    )
    if study_id:
        stmt = stmt.where(Shipment.study_id == study_id)
    if country_id:
        stmt = stmt.where(Site.country_id == country_id)
    if site_id:
        stmt = stmt.where(Shipment.site_id == site_id)
    return [
        _build_delay_candidate(db, shipment, site, country, study)
        for shipment, site, country, study in db.execute(stmt).all()
    ]


def _build_delay_candidate(db, shipment, site, country, study) -> dict[str, Any]:
    days_in_transit = (
        (datetime.utcnow() - shipment.shipped_at).days if shipment.shipped_at else None
    )
    available_kit_count = count_available_kits(
        db, study_id=shipment.study_id, site_id=shipment.site_id, product_label=shipment.product_label
    )
    upcoming_visit_count = count_upcoming_drug_visits(
        db, study_id=shipment.study_id, site_id=shipment.site_id, window_days=UPCOMING_VISIT_WINDOW_DAYS
    )
    severity = (
        "Critical"
        if upcoming_visit_count and available_kit_count == 0
        else "High"
        if upcoming_visit_count
        else "Medium"
    )
    return {
        "issue_type": ISSUE_TYPE,
        "reference_key": f"shipment_delays:{shipment.study_id}:{shipment.shipment_id}",
        "shipment_id": shipment.shipment_id,
        "study_id": shipment.study_id,
        "site_id": shipment.site_id,
        "country": (
            country.country_name
            if country
            else site.country_id
            if site
            else None
        ),
        "depot": shipment.origin_location,
        "carrier_status": shipment.logistics_status,
        "carrier_name": shipment.carrier_name,
        "tracking_number": shipment.tracking_number,
        "product_label": shipment.product_label,
        "requested_at": shipment.requested_at.isoformat() if shipment.requested_at else None,
        "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
        # The current source model does not contain a planned/required-by date.
        "required_by_date": None,
        "days_in_transit": days_in_transit,
        "available_kit_count": available_kit_count,
        "upcoming_drug_visit_count": upcoming_visit_count,
        "severity": severity,
        "supervisor_email": (
            study.supply_manager_email or study.study_manager_email
            if study
            else None
        ),
    }


def shipment_delay_initial_node(state: AgentWorkflowState) -> dict[str, Any]:
    """Create/reuse the issue and recheck the shipment's tracking status."""
    db = state["db"]
    issue = state.get("issue")
    candidate = dict(state.get("candidate") or {})

    if issue is not None and not candidate:
        candidate = _context_for_delay_issue(db, issue)
    if candidate:
        candidate = _refresh_delay_candidate(db, candidate)

    mismatch_exists = candidate.get("carrier_status") == "DELAYED"

    if issue is None and candidate:
        issue = (
            db.query(Issue)
            .filter(Issue.reference_key == candidate["reference_key"])
            .first()
        )
        if issue is None:
            issue = Issue(
                reference_key=candidate["reference_key"],
                issue_type=ISSUE_TYPE,
                risk_type=RISK_TYPE,
                originating_risk_node="Supply/Logistics Node",
                status="Open",
                current_node="Initial Node",
                previous_node=state.get("current_node"),
                severity=candidate["severity"],
                summary=(
                    f"Shipment {candidate['shipment_id']} has been delayed in transit "
                    f"for {candidate['days_in_transit']} day(s) at site {candidate['site_id']}."
                ),
            )
            db.add(issue)
            db.flush()
            _add_initial_delay_evidence(db, issue, candidate)
        elif issue.status == "Closed":
            issue.status = "Open"
            issue.resolved_at = None

    check_in_due = False
    if issue is not None:
        is_waiting = issue.status == "Open" and state["entrypoint"] in {"scan", "verify"}
        if mismatch_exists and is_waiting:
            check_in_due = is_check_in_due(db, issue, action_type="DELAY_STATUS_REQUEST")
        issue.previous_node = state.get("current_node")
        issue.current_node = "Initial Node"
        db.commit()
    else:
        is_waiting = False

    if mismatch_exists and is_waiting and not check_in_due:
        initial_message = (
            "The shipment is still delayed, but the next scheduled check "
            "isn't due yet; continuing to wait."
        )
    elif mismatch_exists:
        initial_message = (
            "Carrier tracking still shows this shipment as delayed; routing to Follow-up Node."
        )
    else:
        initial_message = "Carrier tracking recheck is clear; routing to Closing Node."

    return {
        "issue": issue,
        "issue_id": issue.issue_id if issue else None,
        "candidate": candidate,
        "mismatch_exists": mismatch_exists,
        "check_in_due": check_in_due,
        "closing_origin": "Initial Node" if not mismatch_exists else None,
        "current_node": "Initial Node",
        "events": [
            *state["events"],
            event("Initial Node", initial_message),
        ],
    }


def shipment_delay_follow_up_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue = state["issue"]
    if issue is None:
        raise ValueError("Follow-up Node requires an issue.")

    if issue.follow_up_count >= MAX_FOLLOW_UP_VISITS:
        issue.previous_node = "Follow-up Node"
        issue.current_node = "Closing Node"
        state["db"].commit()
        return {
            "follow_up_allowed": False,
            "email_sent": False,
            "closing_origin": "Follow-up Node",
            "current_node": "Follow-up Node",
            "events": [
                *state["events"],
                event(
                    "Follow-up Node",
                    "Maximum follow-up attempts reached; routing to Closing Node.",
                ),
            ],
        }

    issue.follow_up_count += 1
    issue.previous_node = "Initial Node"
    issue.current_node = "Follow-up Node"
    state["db"].commit()

    candidate = state["candidate"]
    draft = generate_shipment_delay_email(
        issue_id=issue.issue_id,
        candidate=candidate,
        follow_up_count=issue.follow_up_count,
    )
    details = {
        **candidate,
        "ai_model": draft.model_used,
        "ai_prompt": draft.prompt_name,
        "generated_by": "gemini",
    }
    sent = send_and_record(
        state,
        issue=issue,
        action_type="DELAY_STATUS_REQUEST",
        subject=draft.subject,
        body=draft.body,
        due_at=datetime.utcnow() + timedelta(seconds=FOLLOW_UP_INTERVAL_SECONDS),
        details=details,
    )

    if not sent:
        issue.previous_node = "Follow-up Node"
        issue.current_node = "Closing Node"
        state["db"].commit()

    return {
        "follow_up_allowed": True,
        "email_sent": sent,
        "closing_origin": None if sent else "Follow-up Node",
        "status": "open",
        "current_node": "Follow-up Node",
        "events": [
            *state["events"],
            event(
                "Follow-up Node",
                (
                    f"Sent a delay status request; will recheck the tracking status in "
                    f"{FOLLOW_UP_INTERVAL_SECONDS // 60} minute(s) if nothing changes."
                    if sent
                    else "Email delivery failed; routing to Closing Node."
                ),
            ),
        ],
    }


def shipment_delay_closing_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue = state["issue"]
    origin = state["closing_origin"]
    if issue is None or origin is None:
        return {
            "status": "closed",
            "current_node": "Closing Node",
            "events": [
                *state["events"],
                event("Closing Node", "No issue required persistence."),
            ],
        }

    issue.previous_node = origin
    issue.current_node = "Closing Node"
    shipment_id = (state.get("candidate") or {}).get("shipment_id") or "the shipment"
    site_id = (state.get("candidate") or {}).get("site_id") or "the site"
    if origin == "Initial Node":
        issue.status = "Closed"
        issue.resolved_at = datetime.utcnow()
        action_type = "RESOLUTION_NOTIFICATION"
        subject = f"Shipment tracking update for {shipment_id}"
        body = (
            "Hello,\n\n"
            f"Shipment {shipment_id} for site {site_id} is moving again or has arrived, so no further "
            "follow-up is needed at this time.\n\n"
            "Thank you,\n"
            "Clinical Supply Monitoring Team"
        )
        final_status = "closed"
        message = "Closed after tracking verification."
    else:
        issue.status = "Escalated"
        action_type = "HUMAN_ESCALATION"
        subject = f"Human review needed for delayed shipment at {site_id}"
        reason = ESCALATION_REASONS.get(origin, "It could not be resolved automatically.")
        body = (
            "Hello,\n\n"
            f"The delayed shipment {shipment_id} at site {site_id} needs a closer look.\n\n"
            f"{reason}\n\n"
            f"{issue.summary}\n\n"
            "Thank you,\n"
            "Clinical Supply Monitoring Team"
        )
        final_status = "escalated"
        message = f"Escalated because Closing Node was reached from {origin}."
    state["db"].commit()

    send_and_record(
        state,
        issue=issue,
        action_type=action_type,
        subject=subject,
        body=body,
        details={"closing_origin": origin},
    )
    return {
        "status": final_status,
        "current_node": "Closing Node",
        "events": [
            *state["events"],
            event("Closing Node", message),
        ],
    }


def _refresh_delay_candidate(db, context: dict[str, Any]) -> dict[str, Any]:
    shipment = db.get(Shipment, (context.get("study_id"), context.get("shipment_id")))
    if shipment is None:
        return {**context, "carrier_status": None}
    site = db.get(Site, (shipment.study_id, shipment.site_id))
    country = (
        db.get(Country, (site.study_id, site.country_id))
        if site
        else None
    )
    study = db.get(Study, shipment.study_id)
    return _build_delay_candidate(db, shipment, site, country, study)


def _context_for_delay_issue(db, issue: Issue) -> dict[str, Any]:
    action = (
        db.query(IssueAction)
        .filter(IssueAction.issue_id == issue.issue_id)
        .filter(IssueAction.action_type == "DELAY_STATUS_REQUEST")
        .order_by(IssueAction.action_id)
        .first()
    )
    if action and action.details:
        return dict(action.details)
    parts = (issue.reference_key or "").split(":")
    if len(parts) == 3:
        return _refresh_delay_candidate(db, {"study_id": parts[1], "shipment_id": parts[2]})
    return {}


def _add_initial_delay_evidence(db, issue: Issue, candidate: dict[str, Any]) -> None:
    db.add_all(
        [
            IssueEvidence(
                issue_id=issue.issue_id,
                source_system="Carrier tracking",
                evidence_summary=(
                    f"Shipment {candidate['shipment_id']} status is "
                    f"{candidate['carrier_status']}; shipped at "
                    f"{candidate['shipped_at']}; carrier {candidate['carrier_name']}; "
                    f"tracking {candidate['tracking_number']}. It has been in transit "
                    f"for {candidate['days_in_transit']} day(s)."
                ),
            ),
            IssueEvidence(
                issue_id=issue.issue_id,
                source_system="Site inventory",
                evidence_summary=(
                    f"Available backup kits for the product at the site: "
                    f"{candidate['available_kit_count']}."
                ),
            ),
            IssueEvidence(
                issue_id=issue.issue_id,
                source_system="Visit schedule",
                evidence_summary=(
                    f"Study {candidate['study_id']}; site "
                    f"{candidate['site_id']}; country {candidate['country']}; "
                    f"{candidate['upcoming_drug_visit_count']} drug-required "
                    f"visit(s) in the next {UPCOMING_VISIT_WINDOW_DAYS} days."
                ),
            ),
        ]
    )


def get_delay_context_snapshot(db, issue: Issue) -> dict[str, Any] | None:
    """Live view of the shipment behind this issue, for the issue detail page."""
    if issue.issue_type != ISSUE_TYPE:
        return None
    candidate = _context_for_delay_issue(db, issue)
    shipment = db.get(Shipment, (candidate.get("study_id"), candidate.get("shipment_id")))
    if shipment is None:
        return None
    days_in_transit = (
        (datetime.utcnow() - shipment.shipped_at).days if shipment.shipped_at else None
    )
    return {
        "shipment": {
            "study_id": shipment.study_id,
            "shipment_id": shipment.shipment_id,
            "site_id": shipment.site_id,
            "logistics_status": shipment.logistics_status,
            "requested_at": shipment.requested_at,
            "shipped_at": shipment.shipped_at,
            "carrier_name": shipment.carrier_name,
            "tracking_number": shipment.tracking_number,
            "product_label": shipment.product_label,
            "days_in_transit": days_in_transit,
        },
    }
