from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.agent_system import Issue, IssueAction
from app.services.gmail_toolkit_service import (
    RECIPIENT_EMAIL,
    fetch_unread_replies,
    send_email,
)
from app.workflows.delivery_not_registered import (
    complete_reply_processing,
    delivery_closing_node,
    delivery_decision_node,
    delivery_follow_up_node,
    delivery_initial_node,
    find_delivery_candidates,
    is_check_in_due,
    load_issue_for_event_node,
    mark_kits_received,
    record_received_reply,
    resolve_issue_for_reply,
    route_after_decision,
    route_after_follow_up,
    route_after_initial,
    timeout_node,
    update_shipment_fields,
    wait_for_email_node,
    FOLLOW_UP_INTERVAL_SECONDS,
)
from app.workflows.main_node import main_node, route_from_main
from app.workflows.risk_nodes import (
    forecasting_node,
    route_from_risk_node,
    site_level_node,
    software_node,
    supply_logistics_node,
)
from app.workflows.schemas import WorkflowResult
from app.workflows.state import AgentWorkflowState, event


def route_entrypoint(state: AgentWorkflowState) -> str:
    return {
        "scan": "main_node",
        "email_response": "load_issue_for_response",
        "timeout": "load_issue_for_timeout",
        "verify": "load_issue_for_verify",
    }[state["entrypoint"]]


def finish_without_issue_node(state: AgentWorkflowState) -> dict[str, Any]:
    return {
        "status": "closed",
        "current_node": "Finished",
        "events": [
            *state["events"],
            event("Finished", "No supported issue required action."),
        ],
    }


def build_agentic_workflow_graph():
    graph = StateGraph(AgentWorkflowState)
    graph.add_node("main_node", main_node)
    graph.add_node("supply_logistics_node", supply_logistics_node)
    graph.add_node("site_level_node", site_level_node)
    graph.add_node("forecasting_node", forecasting_node)
    graph.add_node("software_node", software_node)
    graph.add_node("delivery_initial_node", delivery_initial_node)
    graph.add_node("delivery_follow_up_node", delivery_follow_up_node)
    graph.add_node("wait_for_email", wait_for_email_node)
    graph.add_node("delivery_decision_node", delivery_decision_node)
    graph.add_node("delivery_closing_node", delivery_closing_node)
    graph.add_node("load_issue_for_response", load_issue_for_event_node)
    graph.add_node("load_issue_for_timeout", load_issue_for_event_node)
    graph.add_node("load_issue_for_verify", load_issue_for_event_node)
    graph.add_node("timeout_node", timeout_node)
    graph.add_node("finish_without_issue", finish_without_issue_node)

    graph.add_conditional_edges(
        START,
        route_entrypoint,
        {
            "main_node": "main_node",
            "load_issue_for_response": "load_issue_for_response",
            "load_issue_for_timeout": "load_issue_for_timeout",
            "load_issue_for_verify": "load_issue_for_verify",
        },
    )
    graph.add_conditional_edges(
        "main_node",
        route_from_main,
        {
            "supply_logistics_node": "supply_logistics_node",
            "site_level_node": "site_level_node",
            "forecasting_node": "forecasting_node",
            "software_node": "software_node",
            "finish_without_issue": "finish_without_issue",
        },
    )
    for risk_node in (
        "supply_logistics_node",
        "site_level_node",
        "forecasting_node",
        "software_node",
    ):
        graph.add_conditional_edges(
            risk_node,
            route_from_risk_node,
            {
                "delivery_initial_node": "delivery_initial_node",
                "finish_without_issue": "finish_without_issue",
            },
        )

    graph.add_conditional_edges(
        "delivery_initial_node",
        route_after_initial,
        {
            "delivery_follow_up_node": "delivery_follow_up_node",
            "delivery_closing_node": "delivery_closing_node",
            "wait_for_email": "wait_for_email",
        },
    )
    graph.add_conditional_edges(
        "delivery_follow_up_node",
        route_after_follow_up,
        {
            "wait_for_email": "wait_for_email",
            "delivery_closing_node": "delivery_closing_node",
        },
    )
    graph.add_edge("load_issue_for_response", "delivery_decision_node")
    graph.add_conditional_edges(
        "delivery_decision_node",
        route_after_decision,
        {
            "delivery_initial_node": "delivery_initial_node",
            "delivery_closing_node": "delivery_closing_node",
        },
    )
    graph.add_edge("load_issue_for_timeout", "timeout_node")
    graph.add_edge("timeout_node", "delivery_closing_node")
    graph.add_edge("load_issue_for_verify", "delivery_initial_node")

    graph.add_edge("wait_for_email", END)
    graph.add_edge("delivery_closing_node", END)
    graph.add_edge("finish_without_issue", END)
    return graph.compile()


agentic_workflow_graph = build_agentic_workflow_graph()


def _initial_state(
    db: Session,
    *,
    entrypoint: Literal["scan", "email_response", "timeout", "verify"],
    candidate: dict[str, Any] | None = None,
    issue_id: int | None = None,
    response_text: str | None = None,
) -> AgentWorkflowState:
    return {
        "db": db,
        "entrypoint": entrypoint,
        "detected_risk_types": [],
        "risk_type": None,
        "issue_type": None,
        "issue_id": issue_id,
        "issue": None,
        "candidate": candidate or {},
        "mismatch_exists": False,
        "check_in_due": False,
        "follow_up_allowed": False,
        "email_sent": False,
        "response_text": response_text,
        "response_outcome": None,
        "closing_origin": None,
        "status": "closed",
        "current_node": START,
        "events": [],
    }


def _result(state: AgentWorkflowState) -> WorkflowResult:
    issue_id = state.get("issue_id")
    issue = state.get("issue")
    return {
        "scenario": "clinical_trial_agentic_workflow",
        "status": state["status"],
        "created_issue_ids": [issue_id] if issue_id else [],
        "reused_issue_ids": [],
        "issue_count": 1 if issue_id else 0,
        "events": state["events"],
        "payload": {
            "risk_type": state.get("risk_type"),
            "issue_type": state.get("issue_type"),
            "issue_id": issue_id,
            "current_node": state["current_node"],
            "follow_up_count": issue.follow_up_count if issue else 0,
            "response_count": issue.response_count if issue else 0,
        },
    }


def run_full_agentic_workflow(db: Session) -> list[WorkflowResult]:
    detected_candidates = find_delivery_candidates(db)
    candidates = [
        candidate
        for candidate in detected_candidates
        if not (
            db.query(Issue)
            .filter(Issue.reference_key == candidate["reference_key"])
            .filter(Issue.status == "Escalated")
            .first()
        )
    ]
    if detected_candidates and not candidates:
        return []
    if not candidates:
        final = agentic_workflow_graph.invoke(
            _initial_state(db, entrypoint="scan")
        )
        return [_result(final)]

    results = []
    for candidate in candidates:
        final = agentic_workflow_graph.invoke(
            _initial_state(
                db,
                entrypoint="scan",
                candidate=candidate,
            )
        )
        results.append(_result(final))
    return results


def continue_issue(
    db: Session,
    *,
    issue_id: int,
    entrypoint: Literal["email_response", "timeout", "verify"],
    response_text: str | None = None,
) -> WorkflowResult:
    final = agentic_workflow_graph.invoke(
        _initial_state(
            db,
            entrypoint=entrypoint,
            issue_id=issue_id,
            response_text=response_text,
        )
    )
    return _result(final)



def process_pending_outbound_emails(db: Session) -> list[dict[str, Any]]:
    """Send any legacy/stuck queued outbound actions through GmailToolkit.

    The current workflow sends synchronously in Follow-up Node, but this worker
    keeps the system safe if an older run or interrupted process left records
    in Queued/Sending state.
    """
    sendable_types = {
        "RECEIPT_REMINDER",
        "RESOLUTION_NOTIFICATION",
        "HUMAN_ESCALATION",
    }
    actions = (
        db.query(IssueAction)
        .filter(IssueAction.action_type.in_(sendable_types))
        .filter(IssueAction.status.in_(["Queued", "Sending"]))
        .order_by(IssueAction.action_id)
        .all()
    )
    processed: list[dict[str, Any]] = []
    for action in actions:
        issue = db.get(Issue, action.issue_id)
        if issue is None:
            action.status = "Failed"
            action.details = {**(action.details or {}), "email_error": "Issue no longer exists."}
            action.completed_at = datetime.utcnow()
            db.commit()
            processed.append({"action_id": action.action_id, "status": action.status})
            continue

        action.status = "Sending"
        action.recipient = action.recipient or RECIPIENT_EMAIL
        db.commit()
        try:
            sent = send_email(
                issue_id=issue.issue_id,
                subject=action.subject or issue.summary,
                body=action.message,
            )
        except Exception as exc:  # noqa: BLE001
            action.status = "Failed"
            action.details = {**(action.details or {}), "email_error": str(exc)}
            action.completed_at = datetime.utcnow()
            db.commit()
            processed.append({"action_id": action.action_id, "status": action.status})
            continue

        sent_at = datetime.utcnow()
        action.status = "Sent"
        action.subject = sent.subject
        action.external_message_id = sent.message_id
        action.completed_at = sent_at
        if action.action_type == "RECEIPT_REMINDER":
            action.due_at = sent_at + timedelta(seconds=FOLLOW_UP_INTERVAL_SECONDS)
        action.details = {
            **(action.details or {}),
            "gmail_thread_id": getattr(sent, "gmail_thread_id", None),
            "gmail_message_id": getattr(sent, "gmail_message_id", None),
            "gmail_rfc_message_id": sent.message_id,
            "raw_tool_result": getattr(sent, "raw_tool_result", ""),
            "sent_via": "langchain_gmail_toolkit",
            "recipient_visible_tracking_token": False,
            "recovered_from_status": "Queued/Sending",
        }
        db.commit()
        processed.append({"action_id": action.action_id, "status": action.status})
    return processed

def process_email_replies(db: Session) -> list[WorkflowResult]:
    results: list[WorkflowResult] = []
    for reply in fetch_unread_replies():
        duplicate_conditions = [IssueAction.email_uid == reply.uid]
        if reply.message_id:
            duplicate_conditions.append(
                IssueAction.external_message_id == reply.message_id
            )
        duplicate = (
            db.query(IssueAction)
            .filter(or_(*duplicate_conditions))
            .first()
        )
        if duplicate:
            complete_reply_processing(reply)
            continue
        issue = resolve_issue_for_reply(db, reply)
        if issue is None or issue.status not in {"Open", "Waiting for Response"}:
            complete_reply_processing(reply)
            continue
        record_received_reply(db, reply, issue)
        result = continue_issue(
            db,
            issue_id=issue.issue_id,
            entrypoint="email_response",
            response_text=reply.body,
        )
        complete_reply_processing(reply)
        results.append(result)
    return results


def process_due_issue_checks(db: Session) -> list[WorkflowResult]:
    """Recheck every Delivery Not Registered issue whose next check-in has arrived.

    This is the primary driver now that the workflow detects fixes by polling
    the database instead of waiting on a site reply: each due issue is
    reverified, which closes it if the mismatch cleared, sends another
    follow-up if it's still pending and under the follow-up cap, or escalates
    once the cap is reached.
    """
    issues = (
        db.query(Issue)
        .filter(Issue.issue_type == "Delivery Not Registered")
        .filter(Issue.status == "Waiting for Response")
        .all()
    )
    results: list[WorkflowResult] = []
    for issue in issues:
        if not is_check_in_due(db, issue):
            continue
        results.append(
            continue_issue(
                db,
                issue_id=issue.issue_id,
                entrypoint="verify",
            )
        )
    return results


def resolve_delivery_issue(db: Session, issue_id: int, kit_ids: list[str] | None = None) -> WorkflowResult:
    """Mark this issue's pending kits (or a chosen subset) as received, then reverify/close it.

    Lets the UI fix a Delivery Not Registered issue directly instead of
    requiring a real inventory system (or manual SQL) to clear the mismatch.
    """
    issue = db.get(Issue, issue_id)
    if issue is None or issue.issue_type != "Delivery Not Registered":
        raise ValueError(f"Delivery Not Registered issue {issue_id} not found.")
    mark_kits_received(db, issue, kit_ids=kit_ids)
    return continue_issue(db, issue_id=issue_id, entrypoint="verify")


def update_delivery_shipment(db: Session, issue_id: int, updates: dict[str, Any]) -> WorkflowResult:
    """Correct the shipment's own data, then reverify/close the issue.

    For when the mismatch turns out to be bad shipment data rather than a
    missed receipt.
    """
    issue = db.get(Issue, issue_id)
    if issue is None or issue.issue_type != "Delivery Not Registered":
        raise ValueError(f"Delivery Not Registered issue {issue_id} not found.")
    update_shipment_fields(db, issue, updates)
    return continue_issue(db, issue_id=issue_id, entrypoint="verify")
