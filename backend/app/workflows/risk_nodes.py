from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.models.source_systems import Kit, Shipment, Visit
from app.workflows.state import AgentWorkflowState, event


def delivery_mismatch_exists(db) -> bool:
    """Shared Supply/Logistics signal: carrier delivered, receipt still pending."""
    return (
        db.query(Shipment)
        .join(
            Kit,
            (Kit.study_id == Shipment.study_id)
            & (Kit.shipment_id == Shipment.shipment_id),
        )
        .filter(Shipment.logistics_status == "DELIVERED")
        .filter(Shipment.delivered_at.is_not(None))
        .filter(Kit.kit_status == "PENDING_RECEIPT")
        .filter(Kit.dispensed_at.is_(None))
        .first()
        is not None
    )


def shipment_delay_exists(db) -> bool:
    """Shared Supply/Logistics signal: a shipment is marked delayed and hasn't arrived."""
    return (
        db.query(Shipment)
        .filter(Shipment.logistics_status == "DELAYED")
        .first()
        is not None
    )


def count_available_kits(db, *, study_id: str, site_id: str, product_label: str | None) -> int:
    """Backup kit stock for a product at a site — shared by every Supply/Logistics issue type."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Kit)
            .where(Kit.study_id == study_id)
            .where(Kit.site_id == site_id)
            .where(Kit.product_label == product_label)
            .where(Kit.kit_status.in_(["AVAILABLE", "RECEIVED"]))
            .where(Kit.dispensed_at.is_(None))
        )
        or 0
    )


def count_upcoming_drug_visits(db, *, study_id: str, site_id: str, window_days: int) -> int:
    """Drug-required visits coming up soon at a site — shared by every Supply/Logistics issue type."""
    now = datetime.utcnow()
    return int(
        db.scalar(
            select(func.count())
            .select_from(Visit)
            .where(Visit.study_id == study_id)
            .where(Visit.site_id == site_id)
            .where(Visit.drug_required.is_(True))
            .where(Visit.visit_at >= now)
            .where(Visit.visit_at <= now + timedelta(days=window_days))
        )
        or 0
    )


def supply_logistics_node(state: AgentWorkflowState) -> dict[str, Any]:
    """
    Isolate a specific issue within Supply/Logistics.

    Current supported classifications:
    - Delivery Not Registered
    - Shipment Delays

    Safety Stock Depletion can be added here without changing the Main Node
    or either issue subgraph.

    When a scan already found a specific candidate, trust the issue type it
    was tagged with rather than re-deriving it — the candidate is the one
    shipment this run is actually about. The global existence checks below
    only apply to the no-candidate fallback scan.
    """
    candidate = state.get("candidate") or {}
    issue_type = candidate.get("issue_type")
    if issue_type is None:
        if delivery_mismatch_exists(state["db"]):
            issue_type = "Delivery Not Registered"
        elif shipment_delay_exists(state["db"]):
            issue_type = "Shipment Delays"

    return {
        "risk_type": "Supply/Logistics",
        "issue_type": issue_type,
        "current_node": "Supply/Logistics Node",
        "events": [
            *state["events"],
            event(
                "Supply/Logistics Node",
                (
                    f"Classified the anomaly as {issue_type}."
                    if issue_type
                    else "No supported Supply/Logistics issue was isolated."
                ),
            ),
        ],
    }


def site_level_node(state: AgentWorkflowState) -> dict[str, Any]:
    return _unsupported_risk_node(state, "Site-Level Node")


def forecasting_node(state: AgentWorkflowState) -> dict[str, Any]:
    return _unsupported_risk_node(state, "Forecasting Node")


def software_node(state: AgentWorkflowState) -> dict[str, Any]:
    return _unsupported_risk_node(state, "Software Node")


def _unsupported_risk_node(
    state: AgentWorkflowState,
    node_name: str,
) -> dict[str, Any]:
    return {
        "issue_type": None,
        "current_node": node_name,
        "events": [
            *state["events"],
            event(node_name, "No issue classifier is implemented for this risk yet."),
        ],
    }


def route_from_risk_node(state: AgentWorkflowState) -> str:
    routes = {
        "Delivery Not Registered": "delivery_initial_node",
        "Shipment Delays": "shipment_delay_initial_node",
    }
    return routes.get(state["issue_type"], "finish_without_issue")
