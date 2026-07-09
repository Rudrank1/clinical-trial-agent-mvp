from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Any

from sqlalchemy import func, select

from app.models.agent_system import Issue, IssueAction, IssueEvidence
from app.models.source_systems import Country, Kit, Shipment, Site, Study, Visit
from app.services.gmail_toolkit_service import (
    RECIPIENT_EMAIL,
    ReceivedReply,
    mark_reply_seen,
    send_email,
)
from app.services.gemini_service import generate_delivery_followup_email
from app.services.response_classifier import classify_delivery_reply
from app.workflows.state import AgentWorkflowState, event

ISSUE_TYPE = "Delivery Not Registered"
RISK_TYPE = "Supply/Logistics"
UPCOMING_VISIT_WINDOW_DAYS = 14
FOLLOW_UP_INTERVAL_SECONDS = int(os.getenv("FOLLOW_UP_INTERVAL_SECONDS", "1200"))
MAX_FOLLOW_UP_VISITS = 2
RECEIPT_INSTRUCTIONS = (
    "Locate the shipment and mark the receipt as complete in whatever system you track it in."
)
ESCALATION_REASONS = {
    "Follow-up Node": "We followed up more than once, but the shipment still hasn't been marked as received.",
    "Decision Node": "The site's reply didn't confirm that the shipment issue has been resolved.",
}


def find_delivery_candidates(
    db,
    *,
    study_id: str | None = None,
    country_id: str | None = None,
    site_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(Shipment, Site, Country, Study)
        .join(
            Kit,
            (Kit.study_id == Shipment.study_id)
            & (Kit.shipment_id == Shipment.shipment_id),
        )
        .join(
            Site,
            (Site.study_id == Shipment.study_id)
            & (Site.site_id == Shipment.site_id),
            isouter=True,
        )
        .join(
            Country,
            (Country.study_id == Site.study_id)
            & (Country.country_id == Site.country_id),
            isouter=True,
        )
        .join(Study, Study.study_id == Shipment.study_id, isouter=True)
        .where(Shipment.logistics_status == "DELIVERED")
        .where(Shipment.delivered_at.is_not(None))
        .where(Kit.kit_status == "PENDING_RECEIPT")
        .where(Kit.dispensed_at.is_(None))
        .distinct()
    )
    if study_id:
        stmt = stmt.where(Shipment.study_id == study_id)
    if country_id:
        stmt = stmt.where(Site.country_id == country_id)
    if site_id:
        stmt = stmt.where(Shipment.site_id == site_id)
    return [
        _build_candidate(db, shipment, site, country, study)
        for shipment, site, country, study in db.execute(stmt).all()
    ]


def _build_candidate(db, shipment, site, country, study) -> dict[str, Any]:
    # Mirrors find_delivery_candidates' definition of "still a mismatch": the
    # shipment has to actually indicate delivered, not just have a pending kit.
    # Matters for _refresh_candidate, which (unlike the initial scan) calls this
    # for a specific already-known shipment with no outer DELIVERED filter — so
    # correcting a shipment's status back off "DELIVERED" must clear the
    # mismatch here too.
    shipment_indicates_delivered = (
        shipment.logistics_status == "DELIVERED" and shipment.delivered_at is not None
    )
    pending_kit_ids = (
        list(
            db.scalars(
                select(Kit.kit_id)
                .where(Kit.study_id == shipment.study_id)
                .where(Kit.shipment_id == shipment.shipment_id)
                .where(Kit.kit_status == "PENDING_RECEIPT")
                .where(Kit.dispensed_at.is_(None))
                .order_by(Kit.kit_id)
            )
        )
        if shipment_indicates_delivered
        else []
    )
    available_kit_count = int(
        db.scalar(
            select(func.count())
            .select_from(Kit)
            .where(Kit.study_id == shipment.study_id)
            .where(Kit.site_id == shipment.site_id)
            .where(Kit.product_label == shipment.product_label)
            .where(Kit.kit_status.in_(["AVAILABLE", "RECEIVED"]))
            .where(Kit.dispensed_at.is_(None))
        )
        or 0
    )
    now = datetime.utcnow()
    upcoming_visit_count = int(
        db.scalar(
            select(func.count())
            .select_from(Visit)
            .where(Visit.study_id == shipment.study_id)
            .where(Visit.site_id == shipment.site_id)
            .where(Visit.drug_required.is_(True))
            .where(Visit.visit_at >= now)
            .where(
                Visit.visit_at
                <= now + timedelta(days=UPCOMING_VISIT_WINDOW_DAYS)
            )
        )
        or 0
    )
    severity = (
        "Critical"
        if upcoming_visit_count and available_kit_count == 0
        else "High"
        if upcoming_visit_count
        else "Medium"
    )
    return {
        "reference_key": (
            f"delivery_not_registered:{shipment.study_id}:"
            f"{shipment.shipment_id}"
        ),
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
        # The current source model does not contain a planned/expected date.
        "expected_delivery_date": None,
        "delivered_at": (
            shipment.delivered_at.isoformat()
            if shipment.delivered_at
            else None
        ),
        "carrier_status": shipment.logistics_status,
        "carrier_name": shipment.carrier_name,
        "tracking_number": shipment.tracking_number,
        # Proof of delivery is not yet represented in the source schema.
        "carrier_proof_of_delivery": None,
        "product_label": shipment.product_label,
        "pending_kit_ids": pending_kit_ids,
        "pending_kit_count": len(pending_kit_ids),
        "available_kit_count": available_kit_count,
        "upcoming_drug_visit_count": upcoming_visit_count,
        "severity": severity,
        "supervisor_email": (
            study.supply_manager_email or study.study_manager_email
            if study
            else None
        ),
    }


def is_check_in_due(db, issue: Issue) -> bool:
    """Whether it's time to recheck this issue's underlying database state.

    An open issue gets rechecked on a timer (the latest reminder's due_at)
    rather than waiting on a site reply, since the workflow now detects
    fixes by polling the source data directly.
    """
    reminder = (
        db.query(IssueAction)
        .filter(IssueAction.issue_id == issue.issue_id)
        .filter(IssueAction.action_type == "RECEIPT_REMINDER")
        .filter(IssueAction.status == "Sent")
        .order_by(IssueAction.action_id.desc())
        .first()
    )
    if reminder is None or reminder.due_at is None:
        return True
    return datetime.utcnow() >= reminder.due_at


def mark_kits_received(db, issue: Issue) -> int:
    """Mark the shipment's receipt as complete, closing the gap the person found.

    Lets the UI resolve a Delivery Not Registered issue directly instead of
    requiring a real inventory system or manual SQL. A shipment's receipt is
    either registered or it isn't — there's no partial state — so this always
    marks every currently-pending kit on the shipment, all at once.
    """
    candidate = _refresh_candidate(db, _context_for_issue(db, issue))
    pending_kit_ids = candidate.get("pending_kit_ids") or []
    if not pending_kit_ids:
        return 0
    updated = (
        db.query(Kit)
        .filter(Kit.study_id == candidate.get("study_id"))
        .filter(Kit.kit_id.in_(pending_kit_ids))
        .update({"kit_status": "RECEIVED"}, synchronize_session=False)
    )
    db.commit()
    return updated


SHIPMENT_EDITABLE_FIELDS = {"logistics_status", "delivered_at", "carrier_name", "tracking_number"}


def update_shipment_fields(db, issue: Issue, updates: dict[str, Any]) -> None:
    """Correct the shipment row itself, for when the mismatch is bad shipment data.

    Only the fields in SHIPMENT_EDITABLE_FIELDS may be changed here.
    """
    candidate = _context_for_issue(db, issue)
    shipment = db.get(Shipment, (candidate.get("study_id"), candidate.get("shipment_id")))
    if shipment is None:
        raise ValueError("Shipment not found for this issue.")
    for field, value in updates.items():
        if field not in SHIPMENT_EDITABLE_FIELDS:
            raise ValueError(f"Field {field!r} is not editable.")
        setattr(shipment, field, value)
    db.commit()


def get_mismatch_snapshot(db, issue: Issue) -> dict[str, Any] | None:
    """Live view of the shipment + kit rows behind this issue, for the fix UI.

    Returns every kit tied to the shipment (not just the pending ones) so the
    person fixing it can see full context, each tagged with whether it's
    currently what's causing the mismatch.
    """
    if issue.issue_type != ISSUE_TYPE:
        return None
    candidate = _context_for_issue(db, issue)
    shipment = db.get(Shipment, (candidate.get("study_id"), candidate.get("shipment_id")))
    if shipment is None:
        return None
    kits = (
        db.query(Kit)
        .filter(Kit.study_id == shipment.study_id)
        .filter(Kit.shipment_id == shipment.shipment_id)
        .order_by(Kit.kit_id)
        .all()
    )
    return {
        "shipment": {
            "study_id": shipment.study_id,
            "shipment_id": shipment.shipment_id,
            "site_id": shipment.site_id,
            "logistics_status": shipment.logistics_status,
            "delivered_at": shipment.delivered_at,
            "carrier_name": shipment.carrier_name,
            "tracking_number": shipment.tracking_number,
            "product_label": shipment.product_label,
        },
        "kits": [
            {
                "kit_id": kit.kit_id,
                "kit_status": kit.kit_status,
                "dispensed_at": kit.dispensed_at,
                "product_label": kit.product_label,
                "expiration_at": kit.expiration_at,
                "pending": kit.kit_status == "PENDING_RECEIPT" and kit.dispensed_at is None,
            }
            for kit in kits
        ],
    }


def delivery_initial_node(state: AgentWorkflowState) -> dict[str, Any]:
    """Create/reuse the issue and perform the report's source-system checks."""
    db = state["db"]
    issue = state.get("issue")
    candidate = dict(state.get("candidate") or {})

    if issue is not None and not candidate:
        candidate = _context_for_issue(db, issue)

    if candidate:
        candidate = _refresh_candidate(db, candidate)

    mismatch_exists = bool(candidate.get("pending_kit_count", 0))

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
                    f"Shipment {candidate['shipment_id']} shows as delivered, but the "
                    f"receipt hasn't been completed at site {candidate['site_id']}."
                ),
            )
            db.add(issue)
            db.flush()
            _add_initial_evidence(db, issue, candidate)
        elif issue.status == "Closed":
            issue.status = "Open"
            issue.resolved_at = None

    check_in_due = False
    if issue is not None:
        is_waiting = issue.status == "Open" and state["entrypoint"] in {"scan", "verify"}
        if mismatch_exists and is_waiting:
            check_in_due = is_check_in_due(db, issue)
        issue.previous_node = state.get("current_node")
        issue.current_node = "Initial Node"
        db.commit()
    else:
        is_waiting = False

    if mismatch_exists and is_waiting and not check_in_due:
        initial_message = (
            "The mismatch remains, but the next scheduled database check "
            "is not due yet; continuing to wait."
        )
    elif mismatch_exists:
        initial_message = (
            "Carrier tracking indicates delivery while the receipt remains "
            "incomplete; routing to Follow-up Node."
        )
    else:
        initial_message = (
            "Source-system recheck is clear; routing to Closing Node."
        )

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


def route_after_initial(state: AgentWorkflowState) -> str:
    issue = state.get("issue")
    if (
        state["mismatch_exists"]
        and issue is not None
        and issue.status == "Open"
        and state["entrypoint"] in {"scan", "verify"}
        and not state.get("check_in_due")
    ):
        return "wait_for_email"
    return (
        "delivery_follow_up_node"
        if state["mismatch_exists"]
        else "delivery_closing_node"
    )


def delivery_follow_up_node(state: AgentWorkflowState) -> dict[str, Any]:
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
                    "Maximum follow-up visits reached; routing to Closing Node.",
                ),
            ],
        }

    issue.follow_up_count += 1
    issue.previous_node = "Initial Node"
    issue.current_node = "Follow-up Node"
    state["db"].commit()

    candidate = state["candidate"]
    draft = generate_delivery_followup_email(
        issue_id=issue.issue_id,
        candidate=candidate,
        follow_up_count=issue.follow_up_count,
        receipt_instructions=RECEIPT_INSTRUCTIONS,
    )
    details = {
        **candidate,
        "ai_model": draft.model_used,
        "ai_prompt": draft.prompt_name,
        "generated_by": "gemini",
    }
    sent = _send_and_record(
        state,
        issue=issue,
        action_type="RECEIPT_REMINDER",
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
                    f"Sent receipt reminder; will recheck the database in "
                    f"{FOLLOW_UP_INTERVAL_SECONDS // 60} minute(s) if nothing changes."
                    if sent
                    else "Email delivery failed; routing to Closing Node."
                ),
            ),
        ],
    }


def route_after_follow_up(state: AgentWorkflowState) -> str:
    if not state["follow_up_allowed"] or not state["email_sent"]:
        return "delivery_closing_node"
    return "wait_for_email"


def wait_for_email_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue = state["issue"]
    assert issue is not None
    issue.status = "Open"
    issue.current_node = "Follow-up Node"
    state["db"].commit()
    return {
        "status": "open",
        "current_node": "Follow-up Node",
        "events": [
            *state["events"],
            event(
                "Follow-up Node",
                "Workflow persisted and paused until the next scheduled database check.",
            ),
        ],
    }


def delivery_decision_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue = state["issue"]
    if issue is None or not state["response_text"]:
        raise ValueError("Decision Node requires an issue and response text.")

    decision = classify_delivery_reply(
        state["response_text"],
        issue_id=issue.issue_id,
        candidate=state.get("candidate") or {},
    )
    outcome = decision.outcome
    response_action = (
        state["db"].query(IssueAction)
        .filter(IssueAction.issue_id == issue.issue_id)
        .filter(IssueAction.action_type == "SITE_EMAIL_RESPONSE")
        .filter(IssueAction.response_type.is_(None))
        .order_by(IssueAction.action_id.desc())
        .first()
    )
    if response_action:
        response_action.response_type = outcome
        response_action.details = {
            **(response_action.details or {}),
            "ai_model": decision.model_used,
            "ai_prompt": decision.prompt_name,
            "ai_confidence": decision.confidence,
            "ai_rationale": decision.rationale,
        }
    issue.response_count += 1
    issue.previous_node = "Follow-up Node"
    issue.current_node = "Decision Node"
    issue.status = "Open"
    state["db"].commit()

    return {
        "response_outcome": outcome,
        "closing_origin": "Decision Node" if outcome != "fixed" else None,
        "current_node": "Decision Node",
        "events": [
            *state["events"],
            event(
                "Decision Node",
                (
                    f"Gemini classified the site response as {outcome} "
                    f"with confidence {decision.confidence:.2f}."
                ),
            ),
        ],
    }


def route_after_decision(state: AgentWorkflowState) -> str:
    if state["response_outcome"] == "fixed":
        return "delivery_initial_node"
    return "delivery_closing_node"


def delivery_closing_node(state: AgentWorkflowState) -> dict[str, Any]:
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
        subject = f"Shipment receipt verified for {shipment_id}"
        body = (
            "Hello,\n\n"
            f"The shipment receipt for {shipment_id} at site {site_id} now looks complete. "
            "No further follow-up is needed at this time.\n\n"
            "Thank you,\n"
            "Clinical Supply Monitoring Team"
        )
        final_status = "closed"
        message = "Closed after source-system verification."
    else:
        issue.status = "Escalated"
        action_type = "HUMAN_ESCALATION"
        subject = f"Human review needed for shipment receipt at {site_id}"
        reason = ESCALATION_REASONS.get(origin, "It could not be resolved automatically.")
        body = (
            "Hello,\n\n"
            f"The shipment receipt mismatch for shipment {shipment_id} at site {site_id} needs a closer look.\n\n"
            f"{reason}\n\n"
            f"{issue.summary}\n\n"
            "Thank you,\n"
            "Clinical Supply Monitoring Team"
        )
        final_status = "escalated"
        message = f"Escalated because Closing Node was reached from {origin}."
    state["db"].commit()

    _send_and_record(
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


def load_issue_for_event_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue_id = state["issue_id"]
    issue = state["db"].get(Issue, issue_id) if issue_id else None
    if issue is None or issue.issue_type != ISSUE_TYPE:
        raise ValueError(f"Delivery Not Registered issue {issue_id} not found.")
    return {
        "issue": issue,
        "candidate": _context_for_issue(state["db"], issue),
        "current_node": issue.current_node or "Initial Node",
    }


def timeout_node(state: AgentWorkflowState) -> dict[str, Any]:
    issue = state["issue"]
    assert issue is not None
    issue.previous_node = "Follow-up Node"
    issue.current_node = "Closing Node"
    state["db"].commit()
    return {
        "closing_origin": "Follow-up Node",
        "current_node": "Follow-up Node",
        "events": [
            *state["events"],
            event(
                "Follow-up Node",
                "No response arrived inside the defined window.",
            ),
        ],
    }


def record_received_reply(db, reply: ReceivedReply, issue: Issue) -> IssueAction:
    existing = None
    if reply.message_id:
        existing = (
            db.query(IssueAction)
            .filter(IssueAction.external_message_id == reply.message_id)
            .first()
        )
    if existing:
        return existing

    (
        db.query(IssueAction)
        .filter(IssueAction.issue_id == issue.issue_id)
        .filter(IssueAction.action_type == "RECEIPT_REMINDER")
        .filter(IssueAction.status == "Sent")
        .update(
            {"status": "Responded", "completed_at": datetime.utcnow()},
            synchronize_session=False,
        )
    )
    action = IssueAction(
        issue_id=issue.issue_id,
        action_type="SITE_EMAIL_RESPONSE",
        status="Received",
        recipient=reply.recipient,
        subject=reply.subject,
        message=reply.body,
        external_message_id=reply.message_id,
        email_uid=reply.uid,
        details={
            "sender": reply.sender,
            "in_reply_to": reply.in_reply_to,
            "references": list(reply.references),
        },
        completed_at=datetime.utcnow(),
    )
    db.add(action)
    db.commit()
    return action


def resolve_issue_for_reply(db, reply: ReceivedReply) -> Issue | None:
    # New natural emails do not expose CTA-ISSUE in the subject/body. Prefer
    # RFC headers and Gmail thread IDs for correlation.
    message_ids = {
        value
        for value in (reply.in_reply_to, *reply.references)
        if value
    }
    if message_ids:
        action = (
            db.query(IssueAction)
            .filter(IssueAction.external_message_id.in_(message_ids))
            .first()
        )
        if action:
            return db.get(Issue, action.issue_id)

    if reply.gmail_thread_id:
        sent_actions = (
            db.query(IssueAction)
            .filter(IssueAction.action_type.in_(["RECEIPT_REMINDER", "RESOLUTION_NOTIFICATION", "HUMAN_ESCALATION"]))
            .all()
        )
        for action in sent_actions:
            details = action.details or {}
            if details.get("gmail_thread_id") == reply.gmail_thread_id:
                return db.get(Issue, action.issue_id)

    # Backward compatibility for old tagged emails already sent before v3.3.
    if reply.issue_id_from_subject:
        return db.get(Issue, reply.issue_id_from_subject)
    return None


def complete_reply_processing(reply: ReceivedReply) -> None:
    mark_reply_seen(reply.uid)


def _refresh_candidate(db, context: dict[str, Any]) -> dict[str, Any]:
    shipment = db.get(
        Shipment,
        (context.get("study_id"), context.get("shipment_id")),
    )
    if shipment is None:
        return {**context, "pending_kit_count": 0, "pending_kit_ids": []}
    site = db.get(Site, (shipment.study_id, shipment.site_id))
    country = (
        db.get(Country, (site.study_id, site.country_id))
        if site
        else None
    )
    study = db.get(Study, shipment.study_id)
    return _build_candidate(db, shipment, site, country, study)


def _context_for_issue(db, issue: Issue) -> dict[str, Any]:
    action = (
        db.query(IssueAction)
        .filter(IssueAction.issue_id == issue.issue_id)
        .filter(IssueAction.action_type == "RECEIPT_REMINDER")
        .order_by(IssueAction.action_id)
        .first()
    )
    if action and action.details:
        return dict(action.details)
    parts = (issue.reference_key or "").split(":")
    if len(parts) == 3:
        return _refresh_candidate(
            db,
            {"study_id": parts[1], "shipment_id": parts[2]},
        )
    return {}


def _add_initial_evidence(db, issue: Issue, candidate: dict[str, Any]) -> None:
    db.add_all(
        [
            IssueEvidence(
                issue_id=issue.issue_id,
                source_system="Carrier tracking",
                evidence_summary=(
                    f"Shipment {candidate['shipment_id']} status is "
                    f"{candidate['carrier_status']}; delivered at "
                    f"{candidate['delivered_at']}; carrier "
                    f"{candidate['carrier_name']}; tracking "
                    f"{candidate['tracking_number']}. Carrier proof of delivery "
                    "is not represented in the current database schema."
                ),
            ),
            IssueEvidence(
                issue_id=issue.issue_id,
                source_system="Site inventory",
                evidence_summary=(
                    f"Kits pending receipt: {', '.join(candidate['pending_kit_ids'])}. "
                    f"Available kits for the product at the site: "
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


def _send_and_record(
    state: AgentWorkflowState,
    *,
    issue: Issue,
    action_type: str,
    subject: str,
    body: str,
    due_at: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    db = state["db"]
    action = IssueAction(
        issue_id=issue.issue_id,
        action_type=action_type,
        status="Sending",
        recipient=RECIPIENT_EMAIL,
        subject=subject,
        message=body,
        due_at=due_at,
        details=details,
    )
    db.add(action)
    db.commit()
    try:
        sent = send_email(issue_id=issue.issue_id, subject=subject, body=body)
    except Exception as exc:  # noqa: BLE001
        action.status = "Failed"
        action.details = {**(details or {}), "email_error": str(exc)}
        action.completed_at = datetime.utcnow()
        db.commit()
        return False

    action.status = "Sent"
    action.external_message_id = sent.message_id
    action.subject = sent.subject
    action.message = body
    action.completed_at = datetime.utcnow()
    action.details = {
        **(details or {}),
        "gmail_thread_id": getattr(sent, "gmail_thread_id", None),
        "gmail_message_id": getattr(sent, "gmail_message_id", None),
        "gmail_rfc_message_id": sent.message_id,
        "raw_tool_result": getattr(sent, "raw_tool_result", ""),
        "sent_via": "langchain_gmail_toolkit",
        "recipient_visible_tracking_token": False,
    }
    db.commit()
    return True
