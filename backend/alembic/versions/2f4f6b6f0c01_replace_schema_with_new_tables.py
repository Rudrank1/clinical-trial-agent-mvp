"""replace schema with new tables

Revision ID: 2f4f6b6f0c01
Revises: 9026547ab435
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f4f6b6f0c01"
down_revision: Union[str, Sequence[str], None] = "9026547ab435"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    old_tables = [
        "issue_evidence",
        "issues",
        "kits",
        "shipments",
        "randomization",
        "visits",
        "subjects",
        "irt_sites",
        "sites",
        "countries",
        "studies",
        "source_treatment_assignments",
        "source_subject_identity_map",
        "source_subject_visits",
        "source_subjects",
        "source_supply_packages",
        "source_shipments",
        "source_site_system_records",
        "source_trial_sites",
        "source_trial_countries",
        "source_trial_studies",
        "carrier_events",
        "site_receipts",
        "irt_inventory",
        "sap_shipments",
    ]

    for table_name in old_tables:
        op.execute(f"DROP TABLE IF EXISTS {table_name}")

    op.execute("SET FOREIGN_KEY_CHECKS = 1")

    op.create_table(
        "studies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("study_status", sa.String(length=50), nullable=False),
        sa.Column("study_manager_name", sa.String(length=100), nullable=True),
        sa.Column("study_manager_email", sa.String(length=150), nullable=True),
        sa.Column("supply_manager_name", sa.String(length=100), nullable=True),
        sa.Column("supply_manager_email", sa.String(length=150), nullable=True),
        sa.Column("planned_subject_total", sa.Integer(), nullable=True),
        sa.Column("actual_subject_total", sa.Integer(), nullable=True),
        sa.Column("planned_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("actual_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("planned_site_total", sa.Integer(), nullable=True),
        sa.Column("active_site_total", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", name="uq_studies_study_code"),
    )

    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("country_label", sa.String(length=100), nullable=False),
        sa.Column("planned_subject_total", sa.Integer(), nullable=True),
        sa.Column("actual_subject_total", sa.Integer(), nullable=True),
        sa.Column("planned_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("actual_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("planned_site_total", sa.Integer(), nullable=True),
        sa.Column("active_site_total", sa.Integer(), nullable=True),
        sa.Column("approval_planned_at", sa.DateTime(), nullable=True),
        sa.Column("approval_actual_at", sa.DateTime(), nullable=True),
        sa.Column("country_status", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code"], ["studies.study_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "country_label", name="uq_countries_study_country"),
    )

    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("site_code", sa.String(length=50), nullable=False),
        sa.Column("site_status", sa.String(length=50), nullable=False),
        sa.Column("planned_activation_date", sa.DateTime(), nullable=True),
        sa.Column("actual_activation_date", sa.DateTime(), nullable=True),
        sa.Column("country_label", sa.String(length=100), nullable=True),
        sa.Column("institution_name", sa.String(length=150), nullable=True),
        sa.Column("investigator_name", sa.String(length=150), nullable=True),
        sa.Column("investigator_email", sa.String(length=150), nullable=True),
        sa.Column("planned_subject_total", sa.Integer(), nullable=True),
        sa.Column("actual_subject_total", sa.Integer(), nullable=True),
        sa.Column("planned_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("actual_enrollment_rate", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code"], ["studies.study_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "site_code", name="uq_sites_study_site"),
    )

    op.create_table(
        "irt_sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("site_code", sa.String(length=50), nullable=False),
        sa.Column("site_system_status", sa.String(length=50), nullable=False),
        sa.Column("site_display_name", sa.String(length=150), nullable=True),
        sa.Column("investigator_name", sa.String(length=150), nullable=True),
        sa.Column("investigator_email", sa.String(length=150), nullable=True),
        sa.Column("country_label", sa.String(length=100), nullable=True),
        sa.Column("site_activated_at", sa.DateTime(), nullable=True),
        sa.Column("site_deactivated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code", "site_code"], ["sites.study_code", "sites.site_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "site_code", name="uq_irt_sites_study_site"),
    )

    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("site_code", sa.String(length=50), nullable=False),
        sa.Column("subject_code", sa.String(length=50), nullable=False),
        sa.Column("randomization_code", sa.String(length=50), nullable=True),
        sa.Column("subject_status", sa.String(length=50), nullable=False),
        sa.Column("country_label", sa.String(length=100), nullable=True),
        sa.Column("next_visit_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code"], ["studies.study_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_code", "site_code"], ["sites.study_code", "sites.site_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "subject_code", name="uq_subjects_study_subject"),
    )

    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("site_code", sa.String(length=50), nullable=False),
        sa.Column("visit_code", sa.String(length=50), nullable=False),
        sa.Column("subject_code", sa.String(length=50), nullable=False),
        sa.Column("visit_at", sa.DateTime(), nullable=False),
        sa.Column("drug_required", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code", "site_code"], ["sites.study_code", "sites.site_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_code", "subject_code"], ["subjects.study_code", "subjects.subject_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "visit_code", name="uq_visits_study_visit"),
    )

    op.create_table(
        "randomization",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("site_code", sa.String(length=50), nullable=False),
        sa.Column("subject_code", sa.String(length=50), nullable=False),
        sa.Column("visit_code", sa.String(length=50), nullable=True),
        sa.Column("randomization_code", sa.String(length=50), nullable=False),
        sa.Column("treatment_label", sa.String(length=100), nullable=True),
        sa.Column("treatment_code", sa.String(length=50), nullable=True),
        sa.Column("randomized_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code", "site_code"], ["sites.study_code", "sites.site_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_code", "subject_code"], ["subjects.study_code", "subjects.subject_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "randomization_code", name="uq_randomization_study_randomization"),
    )

    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("shipment_code", sa.String(length=50), nullable=False),
        sa.Column("origin_location", sa.String(length=100), nullable=True),
        sa.Column("destination_site_code", sa.String(length=50), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("logistics_status", sa.String(length=50), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("carrier_name", sa.String(length=100), nullable=True),
        sa.Column("tracking_code", sa.String(length=100), nullable=True),
        sa.Column("product_label", sa.String(length=100), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code"], ["studies.study_code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_code", "destination_site_code"], ["sites.study_code", "sites.site_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "shipment_code", name="uq_shipments_study_shipment"),
    )

    op.create_table(
        "kits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("study_code", sa.String(length=50), nullable=False),
        sa.Column("kit_code", sa.String(length=50), nullable=False),
        sa.Column("kit_status", sa.String(length=50), nullable=False),
        sa.Column("expiration_at", sa.DateTime(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("dispensed_at", sa.DateTime(), nullable=True),
        sa.Column("site_code", sa.String(length=50), nullable=True),
        sa.Column("subject_code", sa.String(length=50), nullable=True),
        sa.Column("visit_code", sa.String(length=50), nullable=True),
        sa.Column("shipment_code", sa.String(length=50), nullable=True),
        sa.Column("depot_label", sa.String(length=100), nullable=True),
        sa.Column("product_label", sa.String(length=100), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["study_code"], ["studies.study_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_code", "kit_code", name="uq_kits_study_kit"),
    )

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(length=100), nullable=False),
        sa.Column("risk_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_node", sa.String(length=100), nullable=True),
        sa.Column("severity", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "issue_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this destructive schema replacement migration.")
