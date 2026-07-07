"""
Large realistic mock data seeder for the clinical-trial-agent MVP.

This replaces scripts/seed_mock_data.py.

Run from backend folder:
    python scripts/seed_mock_data.py
    python scripts/seed_mock_data.py --scale small
    python scripts/seed_mock_data.py --scale large
    python scripts/seed_mock_data.py --no-clear

The seed is deterministic by default so bugs are reproducible.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from faker import Faker

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

BASE_NOW = datetime(2026, 6, 15, 10, 0, 0)
DEFAULT_SEED = 42

fake = Faker()


@dataclass(frozen=True)
class ScaleConfig:
    studies: int
    countries_per_study: tuple[int, int]
    sites_per_country: tuple[int, int]
    subjects_per_site: tuple[int, int]
    visits_per_subject: tuple[int, int]
    shipments_per_site: tuple[int, int]
    kits_per_shipment: tuple[int, int]
    depot_reserve_kits_per_study: tuple[int, int]


SCALE_CONFIGS: dict[str, ScaleConfig] = {
    "small": ScaleConfig(
        studies=2,
        countries_per_study=(2, 3),
        sites_per_country=(2, 3),
        subjects_per_site=(8, 14),
        visits_per_subject=(3, 4),
        shipments_per_site=(1, 2),
        kits_per_shipment=(5, 10),
        depot_reserve_kits_per_study=(10, 20),
    ),
    "medium": ScaleConfig(
        studies=5,
        countries_per_study=(4, 6),
        sites_per_country=(3, 5),
        subjects_per_site=(18, 35),
        visits_per_subject=(4, 6),
        shipments_per_site=(2, 4),
        kits_per_shipment=(10, 25),
        depot_reserve_kits_per_study=(30, 60),
    ),
    "large": ScaleConfig(
        studies=8,
        countries_per_study=(5, 8),
        sites_per_country=(5, 8),
        subjects_per_site=(35, 70),
        visits_per_subject=(5, 7),
        shipments_per_site=(4, 7),
        kits_per_shipment=(20, 50),
        depot_reserve_kits_per_study=(80, 150),
    ),
}

COUNTRY_POOL: list[tuple[str, str]] = [
    ("US", "United States"),
    ("CA", "Canada"),
    ("GB", "United Kingdom"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("ES", "Spain"),
    ("IT", "Italy"),
    ("NL", "Netherlands"),
    ("BE", "Belgium"),
    ("SE", "Sweden"),
    ("PL", "Poland"),
    ("AU", "Australia"),
    ("JP", "Japan"),
    ("KR", "South Korea"),
    ("IN", "India"),
    ("BR", "Brazil"),
    ("MX", "Mexico"),
    ("ZA", "South Africa"),
]

PRODUCT_LABELS = [
    "Investigational Product 10mg",
    "Investigational Product 25mg",
    "Investigational Product 50mg",
    "Comparator Capsule",
    "Placebo Capsule",
    "Rescue Medication Pack",
]

DEPOTS = [
    "North America Depot",
    "EU Central Depot",
    "APAC Depot",
    "Latin America Depot",
    "UK Depot",
]

CARRIERS = [
    "DHL Clinical Logistics",
    "FedEx Custom Critical",
    "UPS Healthcare",
    "World Courier",
    "Marken",
]

TREATMENTS = [
    ("TRT-A", "Treatment A"),
    ("TRT-B", "Treatment B"),
    ("TRT-C", "Treatment C"),
    ("PBO", "Placebo"),
    ("CMP", "Comparator"),
]

STUDY_STATUSES = ["ACTIVE", "INACTIVE"]
COUNTRY_STATUSES = ["ACTIVE", "INACTIVE"]
SITE_STATUSES = ["ACTIVE", "INACTIVE"]
SUBJECT_STATUSES = ["SCREENED", "RANDOMIZED", "TREATMENT", "COMPLETED"]

# Keep shipment statuses as logistics statuses. Delivery Not Registered detection
# depends on DELIVERED shipments with PENDING_RECEIPT kits, so using subject
# states such as SCREENED/RANDOMIZED for shipments would break the workflow.
SHIPMENT_STATUSES = ["REQUESTED", "IN_TRANSIT", "DELIVERED", "DELAYED", "CANCELLED"]

STUDY_STATUS_WEIGHTS = {
    "ACTIVE": 0.8,
    "INACTIVE": 0.2,
}

COUNTRY_STATUS_WEIGHTS = {
    "ACTIVE": 0.8,
    "INACTIVE": 0.2,
}

SITE_STATUS_WEIGHTS = {
    "ACTIVE": 0.8,
    "INACTIVE": 0.2,
}

SUBJECT_STATUS_WEIGHTS = {
    "SCREENED": 0.25,
    "RANDOMIZED": 0.30,
    "TREATMENT": 0.30,
    "COMPLETED": 0.15,
}

SHIPMENT_STATUS_WEIGHTS = {
    "REQUESTED": 0.10,
    "IN_TRANSIT": 0.20,
    "DELIVERED": 0.62,
    "DELAYED": 0.06,
    "CANCELLED": 0.02,
}


class Counters:
    """Keeps per-run counters for deterministic readable IDs."""

    def __init__(self) -> None:
        self.site = 0
        self.subject = 0
        self.visit = 0
        self.randomization = 0
        self.shipment = 0
        self.kit = 0

    def next_site_id(self, study_number: int) -> str:
        self.site += 1
        return f"SITE-{study_number:03d}-{self.site:04d}"

    def next_subject_id(self, study_number: int) -> str:
        self.subject += 1
        return f"SUBJ-{study_number:03d}-{self.subject:06d}"

    def next_visit_id(self, study_number: int) -> str:
        self.visit += 1
        return f"VIS-{study_number:03d}-{self.visit:07d}"

    def next_randomization_id(self, study_number: int) -> str:
        self.randomization += 1
        return f"RAND-{study_number:03d}-{self.randomization:06d}"

    def next_shipment_id(self, study_number: int) -> str:
        self.shipment += 1
        return f"SHIP-{study_number:03d}-{self.shipment:06d}"

    def next_kit_id(self, study_number: int) -> str:
        self.kit += 1
        return f"KIT-{study_number:03d}-{self.kit:08d}"


def random_date(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """Return a random datetime between start and end."""
    if end <= start:
        return start
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, seconds))


def random_email_for_name(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "." for ch in name).strip(".")
    cleaned = ".".join(part for part in cleaned.split(".") if part)
    if not cleaned:
        cleaned = fake.user_name()
    return f"{cleaned}@example.org"


def weighted_choice(rng: random.Random, choices: Sequence[tuple[str, float]] | dict[str, float]) -> str:
    if isinstance(choices, dict):
        population = list(choices.keys())
        weights = list(choices.values())
    else:
        population = [value for value, _ in choices]
        weights = [weight for _, weight in choices]
    return rng.choices(population, weights=weights, k=1)[0]


def add_in_chunks(db, rows: Sequence[object], chunk_size: int = 1000) -> int:
    if not rows:
        return 0
    total = 0
    for index in range(0, len(rows), chunk_size):
        chunk = list(rows[index:index + chunk_size])
        db.add_all(chunk)
        db.commit()
        total += len(chunk)
    return total


def clear_existing_data(db) -> None:
    """Delete child tables before parent tables to satisfy FK constraints."""
    db.query(IssueAction).delete(synchronize_session=False)
    db.query(IssueEvidence).delete(synchronize_session=False)
    db.query(Issue).delete(synchronize_session=False)

    db.query(Randomization).delete(synchronize_session=False)
    db.query(Visit).delete(synchronize_session=False)
    db.query(Kit).delete(synchronize_session=False)
    db.query(Shipment).delete(synchronize_session=False)
    db.query(Subject).delete(synchronize_session=False)
    db.query(IrtSite).delete(synchronize_session=False)
    db.query(Site).delete(synchronize_session=False)
    db.query(Country).delete(synchronize_session=False)
    db.query(Study).delete(synchronize_session=False)
    db.commit()


def build_study(study_number: int, rng: random.Random) -> Study:
    study_id = f"STUDY-{study_number:03d}"
    study_manager_name = fake.name()
    supply_manager_name = fake.name()

    return Study(
        study_id=study_id,
        source_name="mock_ctms",
        study_status=weighted_choice(rng, STUDY_STATUS_WEIGHTS),
        study_manager_name=study_manager_name,
        study_manager_email=random_email_for_name(study_manager_name),
        supply_manager_name=supply_manager_name,
        supply_manager_email=random_email_for_name(supply_manager_name),
        planned_subject_total=0,
        actual_subject_total=0,
        planned_enrollment_rate=0.0,
        actual_enrollment_rate=0.0,
        planned_site_total=0,
        active_site_total=0,
        updated_at=BASE_NOW - timedelta(days=rng.randint(0, 7)),
    )


def build_country(study_id: str, country_id: str, country_name: str, rng: random.Random) -> Country:
    approval_planned_at = BASE_NOW - timedelta(days=rng.randint(90, 360))
    approval_actual_at = approval_planned_at + timedelta(days=rng.randint(-10, 45))
    return Country(
        study_id=study_id,
        country_id=country_id,
        source_name="mock_ctms",
        country_name=country_name,
        planned_subject_total=0,
        actual_subject_total=0,
        planned_enrollment_rate=0.0,
        actual_enrollment_rate=0.0,
        planned_site_total=0,
        active_site_total=0,
        approval_planned_at=approval_planned_at,
        approval_actual_at=approval_actual_at,
        country_status=weighted_choice(rng, COUNTRY_STATUS_WEIGHTS),
        updated_at=BASE_NOW - timedelta(days=rng.randint(0, 14)),
    )


def build_site(
    study_id: str,
    site_id: str,
    country_id: str,
    rng: random.Random,
) -> tuple[Site, IrtSite]:
    investigator_name = fake.name()
    planned_activation = BASE_NOW - timedelta(days=rng.randint(30, 300))
    actual_activation = planned_activation + timedelta(days=rng.randint(-5, 35))
    site_status = weighted_choice(rng, SITE_STATUS_WEIGHTS)

    if site_status == "INACTIVE" and rng.random() < 0.65:
        actual_activation = None

    site = Site(
        study_id=study_id,
        site_id=site_id,
        country_id=country_id,
        source_name="mock_ctms",
        planned_activation_date=planned_activation,
        actual_activation_date=actual_activation,
        site_status=site_status,
        institution_name=f"{fake.company()} Clinical Research Center",
        investigator_name=investigator_name,
        investigator_email=random_email_for_name(investigator_name),
        planned_subject_total=rng.randint(20, 90),
        actual_subject_total=0,
        planned_enrollment_rate=round(rng.uniform(2.0, 9.0), 2),
        actual_enrollment_rate=0.0,
        updated_at=BASE_NOW - timedelta(days=rng.randint(0, 10)),
    )

    # Mostly mirror CTMS, with a few realistic system mismatches.
    if site_status == "ACTIVE":
        irt_status = weighted_choice(rng, {"ACTIVE": 0.92, "INACTIVE": 0.08})
        site_activated_at = (actual_activation or BASE_NOW - timedelta(days=60)) + timedelta(days=rng.randint(0, 3))
        site_deactivated_at = None
    else:
        irt_status = weighted_choice(rng, {"INACTIVE": 0.90, "ACTIVE": 0.10})
        site_activated_at = actual_activation
        site_deactivated_at = BASE_NOW - timedelta(days=rng.randint(5, 120)) if actual_activation else None

    irt_site = IrtSite(
        study_id=study_id,
        site_id=site_id,
        source_name="mock_irt",
        site_system_status=irt_status,
        site_display_name=f"IRT {site_id}",
        investigator_name=investigator_name,
        investigator_email=random_email_for_name(investigator_name),
        country_name=None,  # filled after country is known, optional/display only
        site_activated_at=site_activated_at,
        site_deactivated_at=site_deactivated_at,
        updated_at=BASE_NOW - timedelta(days=rng.randint(0, 10)),
    )

    return site, irt_site


def build_subjects_and_visits(
    study_number: int,
    study_id: str,
    site_id: str,
    site_activation: datetime | None,
    rng: random.Random,
    counters: Counters,
    subject_count: int,
    visits_per_subject_range: tuple[int, int],
) -> tuple[list[Subject], list[Visit], list[Randomization]]:
    subjects: list[Subject] = []
    visits: list[Visit] = []
    randomizations: list[Randomization] = []

    start_window = site_activation or (BASE_NOW - timedelta(days=180))
    enrollment_start = min(start_window + timedelta(days=7), BASE_NOW - timedelta(days=30))

    for _ in range(subject_count):
        subject_id = counters.next_subject_id(study_number)
        subject_status = weighted_choice(rng, SUBJECT_STATUS_WEIGHTS)

        subject_created_at = random_date(rng, enrollment_start, BASE_NOW - timedelta(days=5))
        visit_count = rng.randint(*visits_per_subject_range)

        subject_visit_ids: list[str] = []
        next_visit_at: datetime | None = None
        randomization_visit_id: str | None = None
        randomized_at: datetime | None = None

        for visit_index in range(visit_count):
            visit_id = counters.next_visit_id(study_number)
            visit_at = subject_created_at + timedelta(days=visit_index * rng.choice([21, 28, 35]))
            drug_required = visit_index > 0 and rng.random() < 0.82

            if visit_at >= BASE_NOW and next_visit_at is None:
                next_visit_at = visit_at

            if visit_index == 1:
                randomization_visit_id = visit_id
                randomized_at = visit_at

            visits.append(
                Visit(
                    study_id=study_id,
                    visit_id=visit_id,
                    subject_id=subject_id,
                    site_id=site_id,
                    source_name="mock_irt",
                    visit_at=visit_at,
                    drug_required=drug_required,
                    updated_at=BASE_NOW - timedelta(days=rng.randint(0, 5)),
                )
            )
            subject_visit_ids.append(visit_id)

        randomization_id: str | None = None
        should_randomize = subject_status in {"RANDOMIZED", "TREATMENT", "COMPLETED"} and rng.random() < 0.82
        if should_randomize:
            randomization_id = counters.next_randomization_id(study_number)
            treatment_id, treatment_label = rng.choice(TREATMENTS)
            randomizations.append(
                Randomization(
                    study_id=study_id,
                    randomization_id=randomization_id,
                    subject_id=subject_id,
                    source_name="mock_irt",
                    site_id=site_id,
                    visit_id=randomization_visit_id,
                    treatment_label=treatment_label,
                    treatment_id=treatment_id,
                    randomized_at=randomized_at or subject_created_at + timedelta(days=14),
                    updated_at=BASE_NOW - timedelta(days=rng.randint(0, 5)),
                )
            )

        subjects.append(
            Subject(
                study_id=study_id,
                subject_id=subject_id,
                site_id=site_id,
                source_name="mock_irt",
                randomization_id=randomization_id,
                subject_status=subject_status,
                next_visit_at=next_visit_at,
                updated_at=BASE_NOW - timedelta(days=rng.randint(0, 5)),
            )
        )

    return subjects, visits, randomizations


def build_shipments_and_kits(
    study_number: int,
    study_id: str,
    site_id: str,
    rng: random.Random,
    counters: Counters,
    shipment_count: int,
    kits_per_shipment_range: tuple[int, int],
    force_dnr: bool = False,
) -> tuple[list[Shipment], list[Kit], int]:
    shipments: list[Shipment] = []
    kits: list[Kit] = []
    dnr_kit_count = 0

    for shipment_index in range(shipment_count):
        shipment_id = counters.next_shipment_id(study_number)
        product_label = rng.choice(PRODUCT_LABELS)
        status = weighted_choice(rng, SHIPMENT_STATUS_WEIGHTS)

        if force_dnr and shipment_index == 0:
            status = "DELIVERED"

        requested_at = BASE_NOW - timedelta(days=rng.randint(5, 180))
        shipped_at = None
        delivered_at = None

        if status in {"IN_TRANSIT", "DELIVERED", "DELAYED"}:
            shipped_at = requested_at + timedelta(days=rng.randint(1, 7))
        if status == "DELIVERED":
            delivered_at = (shipped_at or requested_at) + timedelta(days=rng.randint(1, 10))
            if delivered_at > BASE_NOW - timedelta(days=1):
                delivered_at = BASE_NOW - timedelta(days=rng.randint(1, 3))

        shipment = Shipment(
            study_id=study_id,
            shipment_id=shipment_id,
            site_id=site_id,
            origin_location=rng.choice(DEPOTS),
            requested_at=requested_at,
            shipped_at=shipped_at,
            logistics_status=status,
            delivered_at=delivered_at,
            carrier_name=rng.choice(CARRIERS),
            tracking_number=f"TRK{study_number:03d}{counters.shipment:08d}",
            product_label=product_label,
            updated_at=BASE_NOW - timedelta(days=rng.randint(0, 4)),
        )
        shipments.append(shipment)

        kit_count = rng.randint(*kits_per_shipment_range)
        for kit_index in range(kit_count):
            kit_id = counters.next_kit_id(study_number)
            expiration_at = BASE_NOW + timedelta(days=rng.randint(45, 540))
            released_at = requested_at - timedelta(days=rng.randint(1, 30))
            dispensed_at = None

            is_forced_dnr_kit = force_dnr and shipment_index == 0 and kit_index < max(2, min(5, kit_count))

            if status == "DELIVERED":
                if is_forced_dnr_kit or rng.random() < 0.04:
                    kit_status = "PENDING_RECEIPT"
                    dnr_kit_count += 1
                else:
                    kit_status = weighted_choice(
                        rng,
                        [
                            ("AVAILABLE", 58),
                            ("DISPENSED", 25),
                            ("QUARANTINED", 4),
                            ("EXPIRED", 3),
                            ("RECEIVED", 10),
                        ],
                    )
                    if kit_status == "DISPENSED":
                        dispensed_at = (delivered_at or BASE_NOW - timedelta(days=30)) + timedelta(days=rng.randint(1, 45))
            elif status == "IN_TRANSIT":
                kit_status = "IN_TRANSIT"
            elif status == "DELAYED":
                kit_status = weighted_choice(rng, [("IN_TRANSIT", 70), ("QUARANTINED", 30)])
            elif status == "CANCELLED":
                kit_status = "CANCELLED"
            else:
                kit_status = "RELEASED"

            kits.append(
                Kit(
                    study_id=study_id,
                    kit_id=kit_id,
                    source_name="mock_irt",
                    kit_status=kit_status,
                    shipment_id=shipment_id,
                    expiration_at=expiration_at,
                    released_at=released_at,
                    dispensed_at=dispensed_at,
                    site_id=site_id,
                    depot_label=shipment.origin_location,
                    product_label=product_label,
                    updated_at=BASE_NOW - timedelta(days=rng.randint(0, 4)),
                )
            )

    return shipments, kits, dnr_kit_count


def build_depot_reserve_kits(
    study_number: int,
    study_id: str,
    rng: random.Random,
    counters: Counters,
    count: int,
) -> list[Kit]:
    rows: list[Kit] = []
    for _ in range(count):
        rows.append(
            Kit(
                study_id=study_id,
                kit_id=counters.next_kit_id(study_number),
                source_name="mock_irt",
                kit_status=weighted_choice(rng, [("RELEASED", 75), ("QUARANTINED", 15), ("EXPIRED", 10)]),
                shipment_id=None,
                expiration_at=BASE_NOW + timedelta(days=rng.randint(30, 720)),
                released_at=BASE_NOW - timedelta(days=rng.randint(10, 240)),
                dispensed_at=None,
                site_id=None,
                depot_label=rng.choice(DEPOTS),
                product_label=rng.choice(PRODUCT_LABELS),
                updated_at=BASE_NOW - timedelta(days=rng.randint(0, 10)),
            )
        )
    return rows


def seed_database(scale_name: str, should_clear: bool, seed: int) -> None:
    if scale_name not in SCALE_CONFIGS:
        raise ValueError(f"Unknown scale {scale_name!r}. Expected one of: {', '.join(SCALE_CONFIGS)}")

    config = SCALE_CONFIGS[scale_name]
    rng = random.Random(seed)
    Faker.seed(seed)

    db = SessionLocal()
    totals = {
        "studies": 0,
        "countries": 0,
        "sites": 0,
        "irt_sites": 0,
        "subjects": 0,
        "visits": 0,
        "randomizations": 0,
        "shipments": 0,
        "kits": 0,
        "dnr_kits": 0,
    }

    try:
        if should_clear:
            print("Clearing existing mock data...")
            clear_existing_data(db)

        for study_number in range(1, config.studies + 1):
            counters = Counters()
            study = build_study(study_number, rng)
            db.add(study)
            db.commit()
            totals["studies"] += 1

            selected_countries = rng.sample(COUNTRY_POOL, rng.randint(*config.countries_per_study))
            countries: list[Country] = [
                build_country(study.study_id, country_id, country_name, rng)
                for country_id, country_name in selected_countries
            ]
            add_in_chunks(db, countries)
            totals["countries"] += len(countries)

            all_sites: list[Site] = []
            all_irt_sites: list[IrtSite] = []
            site_country_lookup: dict[tuple[str, str], str] = {}

            for country_id, country_name in selected_countries:
                for _ in range(rng.randint(*config.sites_per_country)):
                    site_id = counters.next_site_id(study_number)
                    site, irt_site = build_site(study.study_id, site_id, country_id, rng)
                    irt_site.country_name = country_name
                    all_sites.append(site)
                    all_irt_sites.append(irt_site)
                    site_country_lookup[(study.study_id, site_id)] = country_id

            add_in_chunks(db, all_sites)
            add_in_chunks(db, all_irt_sites)
            totals["sites"] += len(all_sites)
            totals["irt_sites"] += len(all_irt_sites)

            # Generate subject, visit, and randomization rows site-by-site.
            study_subjects: list[Subject] = []
            study_visits: list[Visit] = []
            study_randomizations: list[Randomization] = []

            for site in all_sites:
                if site.site_status == "INACTIVE":
                    subject_count = rng.randint(0, max(2, config.subjects_per_site[0] // 3))
                else:
                    subject_count = rng.randint(*config.subjects_per_site)

                subjects, visits, randomizations = build_subjects_and_visits(
                    study_number=study_number,
                    study_id=study.study_id,
                    site_id=site.site_id,
                    site_activation=site.actual_activation_date,
                    rng=rng,
                    counters=counters,
                    subject_count=subject_count,
                    visits_per_subject_range=config.visits_per_subject,
                )
                study_subjects.extend(subjects)
                study_visits.extend(visits)
                study_randomizations.extend(randomizations)

                site.actual_subject_total = subject_count
                site.actual_enrollment_rate = round(subject_count / max(1, rng.randint(3, 12)), 2)

            add_in_chunks(db, study_subjects)
            add_in_chunks(db, study_visits)
            add_in_chunks(db, study_randomizations)
            totals["subjects"] += len(study_subjects)
            totals["visits"] += len(study_visits)
            totals["randomizations"] += len(study_randomizations)

            # Generate shipments and kits. Force one DNR case per study for reliable testing.
            study_shipments: list[Shipment] = []
            study_kits: list[Kit] = []
            study_dnr_kits = 0
            force_dnr_used = False

            for site in all_sites:
                shipment_count = rng.randint(*config.shipments_per_site)
                force_dnr = not force_dnr_used and site.site_status == "ACTIVE"
                shipments, kits, dnr_kit_count = build_shipments_and_kits(
                    study_number=study_number,
                    study_id=study.study_id,
                    site_id=site.site_id,
                    rng=rng,
                    counters=counters,
                    shipment_count=shipment_count,
                    kits_per_shipment_range=config.kits_per_shipment,
                    force_dnr=force_dnr,
                )
                if force_dnr:
                    force_dnr_used = True
                study_shipments.extend(shipments)
                study_kits.extend(kits)
                study_dnr_kits += dnr_kit_count

            reserve_kit_count = rng.randint(*config.depot_reserve_kits_per_study)
            study_reserve_kits = build_depot_reserve_kits(
                study_number=study_number,
                study_id=study.study_id,
                rng=rng,
                counters=counters,
                count=reserve_kit_count,
            )

            add_in_chunks(db, study_shipments)
            add_in_chunks(db, study_kits)
            add_in_chunks(db, study_reserve_kits)
            totals["shipments"] += len(study_shipments)
            totals["kits"] += len(study_kits) + len(study_reserve_kits)
            totals["dnr_kits"] += study_dnr_kits

            # Update aggregate totals after children exist.
            study.planned_site_total = len(all_sites)
            study.active_site_total = sum(1 for site in all_sites if site.site_status == "ACTIVE")
            study.planned_subject_total = sum(site.planned_subject_total or 0 for site in all_sites)
            study.actual_subject_total = len(study_subjects)
            study.planned_enrollment_rate = round(sum(site.planned_enrollment_rate or 0 for site in all_sites), 2)
            study.actual_enrollment_rate = round(sum(site.actual_enrollment_rate or 0 for site in all_sites), 2)

            for country in countries:
                country_sites = [site for site in all_sites if site.country_id == country.country_id]
                country.planned_site_total = len(country_sites)
                country.active_site_total = sum(1 for site in country_sites if site.site_status == "ACTIVE")
                country.planned_subject_total = sum(site.planned_subject_total or 0 for site in country_sites)
                country.actual_subject_total = sum(site.actual_subject_total or 0 for site in country_sites)
                country.planned_enrollment_rate = round(sum(site.planned_enrollment_rate or 0 for site in country_sites), 2)
                country.actual_enrollment_rate = round(sum(site.actual_enrollment_rate or 0 for site in country_sites), 2)

            db.commit()

            print(
                f"Seeded {study.study_id}: "
                f"{len(countries)} countries, {len(all_sites)} sites, "
                f"{len(study_subjects)} subjects, {len(study_visits)} visits, "
                f"{len(study_shipments)} shipments, {len(study_kits) + len(study_reserve_kits)} kits, "
                f"{study_dnr_kits} DNR kit signals"
            )

        print("\nDone seeding database.")
        print("Summary:")
        for key, value in totals.items():
            print(f"  {key}: {value}")

        print("\nDelivery Not Registered test signal:")
        print("  shipments.logistics_status = 'DELIVERED'")
        print("  shipments.delivered_at IS NOT NULL")
        print("  kits.kit_status = 'PENDING_RECEIPT'")
        print("  kits.dispensed_at IS NULL")
        print(f"  Expected matching kit rows: {totals['dnr_kits']}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed realistic mock clinical-trial supply data.")
    parser.add_argument(
        "--scale",
        choices=sorted(SCALE_CONFIGS.keys()),
        default="medium",
        help="Dataset size to generate. Default: medium.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducible data. Default: 42.",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not delete existing app data before seeding. Use carefully because PKs may collide.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    seed_database(
        scale_name=args.scale,
        should_clear=not args.no_clear,
        seed=args.seed,
    )