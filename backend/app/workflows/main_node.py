from __future__ import annotations

from typing import Any

from app.workflows.risk_nodes import delivery_mismatch_exists, shipment_delay_exists
from app.workflows.state import AgentWorkflowState, RiskType, event


def _has_supply_logistics_risk(state: AgentWorkflowState) -> bool:
    db = state["db"]
    return delivery_mismatch_exists(db) or shipment_delay_exists(db)


# Add new category-level detectors here as their source data becomes available.
RISK_DETECTORS: dict[RiskType, Any] = {
    "Supply/Logistics": _has_supply_logistics_risk,
}


def main_node(state: AgentWorkflowState) -> dict[str, Any]:
    """Categorize source-system anomalies into broad risk types."""
    detected = [
        risk_type
        for risk_type, detector in RISK_DETECTORS.items()
        if detector(state)
    ]
    return {
        "detected_risk_types": detected,
        "risk_type": detected[0] if detected else None,
        "current_node": "Main Node",
        "events": [
            *state["events"],
            event(
                "Main Node",
                (
                    f"Detected risk categories: {', '.join(detected)}."
                    if detected
                    else "No supported risk category was detected."
                ),
            ),
        ],
    }


def route_from_main(state: AgentWorkflowState) -> str:
    routes = {
        "Supply/Logistics": "supply_logistics_node",
        "Site-Level": "site_level_node",
        "Forecasting": "forecasting_node",
        "Software": "software_node",
    }
    return routes.get(state["risk_type"], "finish_without_issue")
