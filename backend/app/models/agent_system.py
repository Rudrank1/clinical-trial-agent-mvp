from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class Issue(Base):
    __tablename__ = "issues"

    issue_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    reference_key = Column(String(255), nullable=True, unique=True, index=True)
    issue_type = Column(String(100), nullable=False, index=True)
    risk_type = Column(String(100), nullable=False, index=True)
    originating_risk_node = Column(String(100), nullable=True, index=True)
    status = Column(String(50), nullable=False, index=True)
    current_node = Column(String(100), nullable=True)
    previous_node = Column(String(100), nullable=True)
    follow_up_count = Column(Integer, nullable=False, default=0)
    response_count = Column(Integer, nullable=False, default=0)
    severity = Column(String(50), nullable=True)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
    resolved_at = Column(DateTime, nullable=True)

    evidence = relationship(
        "IssueEvidence",
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    actions = relationship(
        "IssueAction",
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="IssueAction.created_at",
    )


class IssueEvidence(Base):
    __tablename__ = "issue_evidence"

    evidence_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    issue_id = Column(
        Integer,
        ForeignKey("issues.issue_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system = Column(String(100), nullable=False)
    evidence_summary = Column(Text, nullable=False)

    issue = relationship("Issue", back_populates="evidence")


class IssueAction(Base):
    """Auditable workflow activity and notification outbox."""

    __tablename__ = "issue_actions"

    action_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    issue_id = Column(
        Integer,
        ForeignKey("issues.issue_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="Recorded", index=True)
    recipient = Column(String(150), nullable=True)
    subject = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    response_type = Column(String(50), nullable=True)
    external_message_id = Column(String(255), nullable=True, unique=True, index=True)
    email_uid = Column(String(100), nullable=True, unique=True, index=True)
    details = Column(JSON, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    issue = relationship("Issue", back_populates="actions")
