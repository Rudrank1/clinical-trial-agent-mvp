from __future__ import annotations

from typing import Any, Literal, TypedDict


WorkflowStatus = Literal["closed", "open", "escalated"]


class WorkflowEvent(TypedDict):
    node: str
    message: str


class WorkflowResult(TypedDict):
    scenario: str
    status: WorkflowStatus
    created_issue_ids: list[int]
    reused_issue_ids: list[int]
    issue_count: int
    events: list[WorkflowEvent]
    payload: dict[str, Any]
