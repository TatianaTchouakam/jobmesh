"""Amazon Jobs connector: field mapping (no network)."""
from jobmesh.connectors.amazonjobs import AmazonJobsConnector


def test_to_job_mapping():
    c = AmazonJobsConnector("all")
    sample = {"id": "123", "title": "Data Engineer", "company_name": "Amazon Web Services",
              "normalized_location": "Berlin, Germany", "job_path": "/en/jobs/123/data-engineer",
              "description": "<p>Build pipelines</p>", "job_schedule_type": "full-time",
              "job_category": "Software Development", "posted_date": "November 26, 2026"}
    j = c._to_job(sample, "2026-11-26T00:00:00Z")
    assert j.title == "Data Engineer" and j.company == "Amazon Web Services"
    assert j.source_url == "https://www.amazon.jobs/en/jobs/123/data-engineer"
    assert j.source_platform == "amazonjobs" and j.is_open is True
    assert j.dedup_key
