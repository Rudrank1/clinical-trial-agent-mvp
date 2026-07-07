from __future__ import annotations

from typing import Any

from app.models.source_systems import Kit, Shipment
from app.workflows.state import AgentWorkflowState, event


def delivery_mismatch_exists(db) -> bool:
    """Shared Supply/Logistics signal: SAP/carrier delivered, IRT receipt still pending."""
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


def supply_logistics_node(state: AgentWorkflowState) -> dict[str, Any]:
    """
    Isolate a specific issue within Supply/Logistics.

    Current supported classifications:
    - Delivery Not Registered

    Shipment Delays and Safety Stock Depletion can be added here without
    changing the Main Node or the delivery issue subgraph.
    """
    issue_type = "Delivery Not Registered" if delivery_mismatch_exists(state["db"]) else None
    return {
        "risk_type": "Supply/Logistics",
        "issue_type": issue_type,
        "current_node": "Supply/Logistics Node",
        "events": [
            *state["events"],
            event(
                "Supply/Logistics Node",
                (
                    "Classified the anomaly as Delivery Not Registered."
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
    }
    return routes.get(state["issue_type"], "finish_without_issue")
