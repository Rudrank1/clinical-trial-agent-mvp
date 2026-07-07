from app.db.database import SessionLocal
from app.models.agent_system import Issue, IssueAction, IssueEvidence
from app.models.source_systems import (
    Country,
    IrtSite,
    Kit,
    Randomization,
    Shipment,
    Site,
    Study,
    Subject,
    Visit,
)


def reset_database_data():
    db = SessionLocal()
    try:
        db.query(IssueAction).delete(synchronize_session=False)
        db.query(IssueEvidence).delete(synchronize_session=False)
        db.query(Issue).delete(synchronize_session=False)
        db.query(Kit).delete(synchronize_session=False)
        db.query(Randomization).delete(synchronize_session=False)
        db.query(Visit).delete(synchronize_session=False)
        db.query(Shipment).delete(synchronize_session=False)
        db.query(Subject).delete(synchronize_session=False)
        db.query(IrtSite).delete(synchronize_session=False)
        db.query(Site).delete(synchronize_session=False)
        db.query(Country).delete(synchronize_session=False)
        db.query(Study).delete(synchronize_session=False)
        db.commit()
        print("Database data cleared successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_database_data()
