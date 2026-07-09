from __future__ import annotations

from typing import Any, Literal, TypedDict

from sqlalchemy.orm import Session

from app.models.agent_system import Issue
from app.workflows.schemas import WorkflowEvent

RiskType = Literal[
    "Supply/Logistics",
    "Site-Level",
    "Forecasting",
    "Software",
]
IssueType = Literal["Delivery Not Registered"]
ClosingOrigin = Literal["Initial Node", "Follow-up Node", "Decision Node"]
DecisionOutcome = Literal["fixed", "no_knowledge", "unclear"]


class AgentWorkflowState(TypedDict):
    db: Session
    entrypoint: Literal["scan", "email_response", "timeout", "verify"]
    detected_risk_types: list[RiskType]
    risk_type: RiskType | None
    issue_type: IssueType | None
    issue_id: int | None
    issue: Issue | None
    candidate: dict[str, Any]
    mismatch_exists: bool
    check_in_due: bool
    follow_up_allowed: bool
    email_sent: bool
    response_text: str | None
    response_outcome: DecisionOutcome | None
    closing_origin: ClosingOrigin | None
    status: Literal["closed", "open", "escalated"]
    current_node: str
    events: list[WorkflowEvent]


def event(node: str, message: str) -> WorkflowEvent:
    return {"node": node, "message": message}
