"""Tests for seniority/experience-level detection and filtering."""

from __future__ import annotations

import os
import tempfile

from jobmesh import storage
from jobmesh.models import Job
from jobmesh.normalize import normalize_level


def test_level_detection_covers_all_buckets():
    cases = {
        "Data Engineering Internship": "Internship",
        "Praktikum Marketing (m/w/d)": "Internship",
        "Stagiaire développeur": "Internship",
        "Ausbildung zum Fachinformatiker": "Apprenticeship",
        "Graduate Program 2026": "Apprenticeship",
        "Working Student Data Analytics": "Working Student",
        "Werkstudent Logistik": "Working Student",
        "Junior Data Analyst": "Junior / Entry",
        "Entry-Level Software Developer": "Junior / Entry",
        "Senior Backend Engineer": "Senior",
        "Lead Data Scientist": "Lead / Principal",
        "Head of Operations": "Lead / Principal",
        "Engineering Manager": "Manager",
        # precedence: junior-side and management win over plain "senior"
        "Senior Manager, Finance": "Manager",
        "Junior Project Manager": "Junior / Entry",
        # no level signal -> None (kept out of the facet)
        "Registered Nurse": None,
        "Warehouse Operative": None,
    }
    for title, expected in cases.items():
        assert normalize_level(title) == expected, title


def test_level_from_employment_type():
    # Some ATSs carry the level in the job-type field, not the title.
    assert normalize_level("Marketing Associate", "Internship") == "Internship"


def test_level_facet_and_filter_end_to_end():
    db = tempfile.mktemp(suffix=".db")
    jobs = [
        Job("greenhouse", "acme", "1", "Data Engineering Internship", "Acme", "Berlin"),
        Job("greenhouse", "acme", "2", "Senior Backend Engineer", "Acme", "Berlin"),
        Job("lever", "beta", "3", "Junior Data Analyst", "Beta", "Lagos"),
        Job("lever", "beta", "4", "Registered Nurse", "Beta", "Nairobi"),
    ]
    try:
        with storage.session(db) as c:
            storage.upsert_jobs(c, jobs)
        with storage.session(db) as c:
            fac = storage.facets(c)
            assert fac["level"] == {"Senior": 1, "Junior / Entry": 1, "Internship": 1}
            assert [r["title"] for r in storage.search(c, level="Internship")] == \
                ["Data Engineering Internship"]
            assert storage.count(c, level="Junior / Entry") == 1
            # a posting with no detected level is excluded from the facet
            assert "Registered Nurse" not in fac["level"]
    finally:
        if os.path.exists(db):
            os.remove(db)
