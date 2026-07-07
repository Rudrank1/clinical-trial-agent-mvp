from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class Study(Base):
    __tablename__ = "studies"

    study_id = Column(String(50), primary_key=True, index=True)
    source_name = Column(String(50), nullable=False, default="mock_ctms")
    study_status = Column(String(50), nullable=False)
    study_manager_name = Column(String(100), nullable=True)
    study_manager_email = Column(String(150), nullable=True)
    supply_manager_name = Column(String(100), nullable=True)
    supply_manager_email = Column(String(150), nullable=True)
    planned_subject_total = Column(Integer, nullable=True)
    actual_subject_total = Column(Integer, nullable=True)
    planned_enrollment_rate = Column(Float, nullable=True)
    actual_enrollment_rate = Column(Float, nullable=True)
    planned_site_total = Column(Integer, nullable=True)
    active_site_total = Column(Integer, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    countries = relationship("Country", back_populates="study", cascade="all, delete-orphan")
    kits = relationship("Kit", back_populates="study", cascade="all, delete-orphan")


class Country(Base):
    __tablename__ = "countries"

    study_id = Column(String(50), primary_key=True, index=True)
    country_id = Column(String(50), primary_key=True, index=True)
    source_name = Column(String(50), nullable=False, default="mock_ctms")
    country_name = Column(String(100), nullable=False)
    planned_subject_total = Column(Integer, nullable=True)
    actual_subject_total = Column(Integer, nullable=True)
    planned_enrollment_rate = Column(Float, nullable=True)
    actual_enrollment_rate = Column(Float, nullable=True)
    planned_site_total = Column(Integer, nullable=True)
    active_site_total = Column(Integer, nullable=True)
    approval_planned_at = Column(DateTime, nullable=True)
    approval_actual_at = Column(DateTime, nullable=True)
    country_status = Column(String(50), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    study = relationship("Study", back_populates="countries")
    sites = relationship("Site", back_populates="country", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(["study_id"], ["studies.study_id"], ondelete="CASCADE"),
        Index("ix_countries_study_country", "study_id", "country_id"),
    )


class Site(Base):
    __tablename__ = "sites"

    study_id = Column(String(50), primary_key=True, index=True)
    site_id = Column(String(50), primary_key=True, index=True)
    country_id = Column(String(50), nullable=False, index=True)
    source_name = Column(String(50), nullable=False, default="mock_ctms")
    planned_activation_date = Column(DateTime, nullable=True)
    actual_activation_date = Column(DateTime, nullable=True)
    site_status = Column(String(50), nullable=False)
    institution_name = Column(String(150), nullable=True)
    investigator_name = Column(String(150), nullable=True)
    investigator_email = Column(String(150), nullable=True)
    planned_subject_total = Column(Integer, nullable=True)
    actual_subject_total = Column(Integer, nullable=True)
    planned_enrollment_rate = Column(Float, nullable=True)
    actual_enrollment_rate = Column(Float, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    country = relationship("Country", back_populates="sites")
    irt_site = relationship("IrtSite", back_populates="site", uselist=False, cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="site", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="site", cascade="all, delete-orphan")
    visits = relationship("Visit", back_populates="site", cascade="all, delete-orphan")
    randomizations = relationship("Randomization", back_populates="site", cascade="all, delete-orphan")
    kits = relationship("Kit", back_populates="site")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "country_id"],
            ["countries.study_id", "countries.country_id"],
            name="fk_sites_country",
        ),
        Index("ix_sites_study_site", "study_id", "site_id"),
    )


class IrtSite(Base):
    __tablename__ = "irt_sites"

    study_id = Column(String(50), primary_key=True, index=True)
    site_id = Column(String(50), primary_key=True, index=True)
    source_name = Column(String(50), nullable=False, default="mock_irt")
    site_system_status = Column(String(50), nullable=False)
    site_display_name = Column(String(150), nullable=True)
    investigator_name = Column(String(150), nullable=True)
    investigator_email = Column(String(150), nullable=True)
    country_name = Column(String(100), nullable=True)
    site_activated_at = Column(DateTime, nullable=True)
    site_deactivated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    site = relationship("Site", back_populates="irt_site")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_irt_sites_site",
            ondelete="CASCADE",
        ),
        Index("ix_irt_sites_study_site", "study_id", "site_id"),
    )


class Subject(Base):
    __tablename__ = "subjects"

    study_id = Column(String(50), primary_key=True, index=True)
    subject_id = Column(String(50), primary_key=True, index=True)
    site_id = Column(String(50), nullable=False, index=True)
    source_name = Column(String(50), nullable=False, default="mock_irt")
    randomization_id = Column(String(50), nullable=True, index=True)
    subject_status = Column(String(50), nullable=False)
    next_visit_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    site = relationship("Site", back_populates="subjects")
    visits = relationship("Visit", back_populates="subject", cascade="all, delete-orphan")
    randomizations = relationship("Randomization", back_populates="subject", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_subjects_site",
            ondelete="CASCADE",
        ),
        Index("ix_subjects_study_site", "study_id", "site_id"),
    )


class Shipment(Base):
    __tablename__ = "shipments"

    study_id = Column(String(50), primary_key=True, index=True)
    shipment_id = Column(String(50), primary_key=True, index=True)
    site_id = Column(String(50), nullable=False, index=True)
    origin_location = Column(String(100), nullable=True)
    requested_at = Column(DateTime, nullable=True)
    shipped_at = Column(DateTime, nullable=True)
    logistics_status = Column(String(50), nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    carrier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    product_label = Column(String(100), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    site = relationship("Site", back_populates="shipments")
    kits = relationship("Kit", back_populates="shipment")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_shipments_site",
            ondelete="CASCADE",
        ),
        Index("ix_shipments_study_site", "study_id", "site_id"),
    )


class Kit(Base):
    __tablename__ = "kits"

    study_id = Column(String(50), primary_key=True, index=True)
    kit_id = Column(String(50), primary_key=True, index=True)
    source_name = Column(String(50), nullable=False, default="mock_irt")
    kit_status = Column(String(50), nullable=False)
    shipment_id = Column(String(50), nullable=True, index=True)
    expiration_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)
    dispensed_at = Column(DateTime, nullable=True)
    site_id = Column(String(50), nullable=True, index=True)
    depot_label = Column(String(100), nullable=True)
    product_label = Column(String(100), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    study = relationship("Study", back_populates="kits")
    shipment = relationship("Shipment", back_populates="kits")
    site = relationship("Site", back_populates="kits")

    __table_args__ = (
        ForeignKeyConstraint(["study_id"], ["studies.study_id"], name="fk_kits_study", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["study_id", "shipment_id"],
            ["shipments.study_id", "shipments.shipment_id"],
            name="fk_kits_shipment",
        ),
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_kits_site",
        ),
        Index("ix_kits_study_shipment", "study_id", "shipment_id"),
        Index("ix_kits_study_site", "study_id", "site_id"),
    )


class Visit(Base):
    __tablename__ = "visits"

    study_id = Column(String(50), primary_key=True, index=True)
    visit_id = Column(String(50), primary_key=True, index=True)
    subject_id = Column(String(50), nullable=False, index=True)
    site_id = Column(String(50), nullable=False, index=True)
    source_name = Column(String(50), nullable=False, default="mock_irt")
    visit_at = Column(DateTime, nullable=False)
    drug_required = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    subject = relationship("Subject", back_populates="visits")
    site = relationship("Site", back_populates="visits")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "subject_id"],
            ["subjects.study_id", "subjects.subject_id"],
            name="fk_visits_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_visits_site",
            ondelete="CASCADE",
        ),
        Index("ix_visits_study_subject", "study_id", "subject_id"),
    )


class Randomization(Base):
    __tablename__ = "randomization"

    study_id = Column(String(50), primary_key=True, index=True)
    randomization_id = Column(String(50), primary_key=True, index=True)
    subject_id = Column(String(50), nullable=False, index=True)
    source_name = Column(String(50), nullable=False, default="mock_irt")
    site_id = Column(String(50), nullable=False, index=True)
    visit_id = Column(String(50), nullable=True, index=True)
    treatment_label = Column(String(100), nullable=True)
    treatment_id = Column(String(50), nullable=True)
    randomized_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    subject = relationship("Subject", back_populates="randomizations")
    site = relationship("Site", back_populates="randomizations")

    __table_args__ = (
        ForeignKeyConstraint(
            ["study_id", "subject_id"],
            ["subjects.study_id", "subjects.subject_id"],
            name="fk_randomization_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["study_id", "site_id"],
            ["sites.study_id", "sites.site_id"],
            name="fk_randomization_site",
            ondelete="CASCADE",
        ),
        Index("ix_randomization_study_subject", "study_id", "subject_id"),
    )