import os
import time

from app.db.database import SessionLocal
from app.workflows.orchestrator import (
    process_due_issue_checks,
    process_email_replies,
    process_pending_outbound_emails,
)

POLL_INTERVAL_SECONDS = int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "30"))


def run_worker():
    print(
        "Email workflow worker started; polling every "
        f"{POLL_INTERVAL_SECONDS} seconds."
    )
    while True:
        db = SessionLocal()
        try:
            outbound = process_pending_outbound_emails(db)
            replies = process_email_replies(db)
            due_checks = process_due_issue_checks(db)
            if outbound or replies or due_checks:
                print(
                    f"Sent/recovered {len(outbound)} outbound email(s), "
                    f"processed {len(replies)} email reply/replies and "
                    f"{len(due_checks)} due database check(s)."
                )
        except Exception as exc:
            db.rollback()
            print(f"Email workflow worker error: {exc}")
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker()
