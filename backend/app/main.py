from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import random

from app.db.database import SessionLocal
from app.models.agent_system import Issue, IssueAction
from app.models.source_systems import Country, Kit, Shipment, Site, Study, Subject
from app.workflows.delivery_not_registered import get_mismatch_snapshot
from app.workflows.orchestrator import (
    continue_issue,
    process_due_issue_checks,
    process_email_replies,
    process_pending_outbound_emails,
    resolve_delivery_issue,
    run_full_agentic_workflow,
    update_delivery_shipment,
)
from scripts.reset_database import reset_database_data
from scripts.seed_mock_data import seed_database

app = FastAPI(title="Clinical Trial Agent MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SiteResponseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class DetectionScopeRequest(BaseModel):
    study_id: str | None = None
    country_id: str | None = None
    site_id: str | None = None


class ShipmentUpdateRequest(BaseModel):
    logistics_status: str | None = None
    delivered_at: datetime | None = None
    carrier_name: str | None = None
    tracking_number: str | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "Clinical Trial Agent MVP backend is running"}


@app.post("/seed_data")
def seed_data():
    seed_database(scale_name="small", should_clear=True, seed=random.randint(1, 1000))
    return {"message": "Database seeded successfully."}


@app.post("/workflows/run")
def run_complete_agentic_workflow(
    request: DetectionScopeRequest | None = None,
    db: Session = Depends(get_db),
):
    """Main Node -> Risk Node -> Issue workflow, optionally scoped to a study/country/site."""
    scope = request or DetectionScopeRequest()
    return {
        "results": run_full_agentic_workflow(
            db,
            study_id=scope.study_id,
            country_id=scope.country_id,
            site_id=scope.site_id,
        )
    }


@app.post("/workflows/delivery_not_registered/issues/{issue_id}/respond")
def record_delivery_issue_response(
    issue_id: int,
    request: SiteResponseRequest,
    db: Session = Depends(get_db),
):
    try:
        return continue_issue(
            db,
            issue_id=issue_id,
            entrypoint="email_response",
            response_text=request.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/workflows/delivery_not_registered/issues/{issue_id}/verify")
def verify_delivery_issue(issue_id: int, db: Session = Depends(get_db)):
    try:
        return continue_issue(
            db,
            issue_id=issue_id,
            entrypoint="verify",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/workflows/delivery_not_registered/issues/{issue_id}/mark-received")
def mark_delivery_issue_received(issue_id: int, db: Session = Depends(get_db)):
    """Mark the issue's shipment as received and reverify/close it.

    Lets the UI fix the underlying mismatch directly, without a real
    inventory system or manual SQL. A shipment's receipt is either complete
    or it isn't, so this always marks the whole shipment's pending kits.
    """
    try:
        return resolve_delivery_issue(db, issue_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/workflows/delivery_not_registered/issues/{issue_id}/shipment")
def update_delivery_issue_shipment(
    issue_id: int,
    request: ShipmentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Correct the shipment's own fields directly and reverify/close the issue."""
    updates = request.model_dump(exclude_unset=True)
    try:
        return update_delivery_shipment(db, issue_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/workflows/email/send-pending")
def send_pending_workflow_emails(db: Session = Depends(get_db)):
    try:
        processed = process_pending_outbound_emails(db)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"processed_count": len(processed), "results": processed}


@app.post("/workflows/email/poll")
def poll_workflow_email_replies(db: Session = Depends(get_db)):
    try:
        outbound = process_pending_outbound_emails(db)
        results = process_email_replies(db)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "sent_pending_count": len(outbound),
        "processed_count": len(results),
        "outbound_results": outbound,
        "results": results,
    }


@app.post("/workflows/check-due-issues")
def check_due_issues(db: Session = Depends(get_db)):
    """Recheck every issue whose next scheduled database check has arrived."""
    results = process_due_issue_checks(db)
    return {"processed_count": len(results), "results": results}


@app.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    totals = {
        "studies": db.query(Study).count(),
        "countries": db.query(Country).count(),
        "sites": db.query(Site).count(),
        "patients": db.query(Subject).count(),
        "shipments": db.query(Shipment).count(),
        "kits": db.query(Kit).count(),
    }
    status_counts = dict(
        db.query(Issue.status, func.count(Issue.issue_id)).group_by(Issue.status).all()
    )
    issues_by_status = {
        status: status_counts.get(status, 0)
        for status in ("Open", "Escalated", "Closed")
    }
    return {"totals": totals, "issues_by_status": issues_by_status}


@app.get("/studies")
def get_studies(db: Session = Depends(get_db)):
    studies = db.query(Study).order_by(Study.study_id).all()
    result = []
    for study in studies:
        # Issue has no study_id column; reference_key encodes it as
        # "<issue_type>:<study_id>:<...>" for every issue type built so far.
        open_issues = (
            db.query(Issue)
            .filter(Issue.reference_key.like(f"%:{study.study_id}:%"))
            .filter(Issue.status.in_(["Open", "Escalated"]))
            .count()
        )
        result.append(
            {
                "study_id": study.study_id,
                "study_status": study.study_status,
                "countries": db.query(Country).filter(Country.study_id == study.study_id).count(),
                "sites": db.query(Site).filter(Site.study_id == study.study_id).count(),
                "patients": db.query(Subject).filter(Subject.study_id == study.study_id).count(),
                "open_issues": open_issues,
            }
        )
    return result


@app.get("/studies/{study_id}/sites")
def get_study_sites(study_id: str, db: Session = Depends(get_db)):
    study = db.get(Study, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found.")

    sites = db.query(Site).filter(Site.study_id == study_id).order_by(Site.site_id).all()
    return {
        "study_id": study.study_id,
        "study_status": study.study_status,
        "sites": [
            {
                "site_id": site.site_id,
                "country_id": site.country_id,
                "site_status": site.site_status,
                "institution_name": site.institution_name,
                "investigator_name": site.investigator_name,
                "patients": db.query(Subject)
                .filter(Subject.study_id == study_id, Subject.site_id == site.site_id)
                .count(),
                "shipments": db.query(Shipment)
                .filter(Shipment.study_id == study_id, Shipment.site_id == site.site_id)
                .count(),
            }
            for site in sites
        ],
    }


@app.get("/countries")
def get_countries(study_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Country)
    if study_id:
        query = query.filter(Country.study_id == study_id)
    countries = query.order_by(Country.study_id, Country.country_id).all()

    return [
        {
            "study_id": country.study_id,
            "country_id": country.country_id,
            "country_name": country.country_name,
            "country_status": country.country_status,
            "sites": db.query(Site)
            .filter(Site.study_id == country.study_id, Site.country_id == country.country_id)
            .count(),
            "patients": db.query(Subject)
            .join(Site, (Site.study_id == Subject.study_id) & (Site.site_id == Subject.site_id))
            .filter(Site.study_id == country.study_id, Site.country_id == country.country_id)
            .count(),
        }
        for country in countries
    ]


@app.get("/sites")
def get_sites(study_id: str | None = None, country_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Site)
    if study_id:
        query = query.filter(Site.study_id == study_id)
    if country_id:
        query = query.filter(Site.country_id == country_id)
    sites = query.order_by(Site.study_id, Site.site_id).all()

    return [
        {
            "study_id": site.study_id,
            "site_id": site.site_id,
            "country_id": site.country_id,
            "site_status": site.site_status,
            "institution_name": site.institution_name,
            "investigator_name": site.investigator_name,
            "patients": db.query(Subject)
            .filter(Subject.study_id == site.study_id, Subject.site_id == site.site_id)
            .count(),
            "shipments": db.query(Shipment)
            .filter(Shipment.study_id == site.study_id, Shipment.site_id == site.site_id)
            .count(),
        }
        for site in sites
    ]


@app.get("/patients")
def get_patients(study_id: str | None = None, site_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Subject)
    if study_id:
        query = query.filter(Subject.study_id == study_id)
    if site_id:
        query = query.filter(Subject.site_id == site_id)
    subjects = query.order_by(Subject.study_id, Subject.subject_id).all()

    return [
        {
            "study_id": subject.study_id,
            "subject_id": subject.subject_id,
            "site_id": subject.site_id,
            "subject_status": subject.subject_status,
            "next_visit_at": subject.next_visit_at,
        }
        for subject in subjects
    ]


@app.get("/shipments")
def get_shipments(study_id: str | None = None, site_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Shipment)
    if study_id:
        query = query.filter(Shipment.study_id == study_id)
    if site_id:
        query = query.filter(Shipment.site_id == site_id)
    shipments = query.order_by(Shipment.study_id, Shipment.shipment_id).all()

    return [
        {
            "study_id": shipment.study_id,
            "shipment_id": shipment.shipment_id,
            "site_id": shipment.site_id,
            "logistics_status": shipment.logistics_status,
            "delivered_at": shipment.delivered_at,
            "carrier_name": shipment.carrier_name,
            "tracking_number": shipment.tracking_number,
            "product_label": shipment.product_label,
        }
        for shipment in shipments
    ]


@app.get("/kits")
def get_kits(study_id: str | None = None, shipment_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Kit)
    if study_id:
        query = query.filter(Kit.study_id == study_id)
    if shipment_id:
        query = query.filter(Kit.shipment_id == shipment_id)
    kits = query.order_by(Kit.study_id, Kit.kit_id).all()

    return [
        {
            "study_id": kit.study_id,
            "kit_id": kit.kit_id,
            "shipment_id": kit.shipment_id,
            "site_id": kit.site_id,
            "kit_status": kit.kit_status,
            "dispensed_at": kit.dispensed_at,
            "product_label": kit.product_label,
            "expiration_at": kit.expiration_at,
        }
        for kit in kits
    ]


@app.get("/issues")
def get_issues(db: Session = Depends(get_db)):
    issues = db.query(Issue).all()

    return [
        {
            "id": issue.issue_id,
            "issue_type": issue.issue_type,
            "risk_type": issue.risk_type,
            "status": issue.status,
            "current_node": issue.current_node,
            "severity": issue.severity,
            "summary": issue.summary,
            "follow_up_count": issue.follow_up_count,
        }
        for issue in issues
    ]


@app.get("/issues/{issue_id}")
def get_issue(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found.")

    actions = (
        db.query(IssueAction)
        .filter(IssueAction.issue_id == issue_id)
        .order_by(IssueAction.action_id)
        .all()
    )
    return {
        "id": issue.issue_id,
        "reference_key": issue.reference_key,
        "issue_type": issue.issue_type,
        "risk_type": issue.risk_type,
        "originating_risk_node": issue.originating_risk_node,
        "status": issue.status,
        "current_node": issue.current_node,
        "previous_node": issue.previous_node,
        "follow_up_count": issue.follow_up_count,
        "response_count": issue.response_count,
        "severity": issue.severity,
        "summary": issue.summary,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "resolved_at": issue.resolved_at,
        "mismatch": get_mismatch_snapshot(db, issue),
        "evidence": [
            {
                "id": evidence.evidence_id,
                "source_system": evidence.source_system,
                "summary": evidence.evidence_summary,
            }
            for evidence in issue.evidence
        ],
        "actions": [
            {
                "id": action.action_id,
                "type": action.action_type,
                "status": action.status,
                "recipient": action.recipient,
                "subject": action.subject,
                "message": action.message,
                "response_type": action.response_type,
                "external_message_id": action.external_message_id,
                "email_uid": action.email_uid,
                "details": action.details,
                "due_at": action.due_at,
                "created_at": action.created_at,
                "completed_at": action.completed_at,
            }
            for action in actions
        ],
    }


@app.post("/reset-database")
def reset_database():
    reset_database_data()
    return {"message": "Database data cleared successfully."}
