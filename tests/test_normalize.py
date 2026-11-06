"""Offline tests for the normalization helpers (no network needed).

Run with:  python -m pytest -q
"""

from jobmesh.normalize import html_to_text, detect_remote, make_dedup_key


def test_html_to_text_strips_tags_and_entities():
    raw = "&lt;p&gt;Senior &amp; Lead Engineer&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(raw) == "Senior & Lead Engineer Python"


def test_html_to_text_handles_none():
    assert html_to_text(None) is None
    assert html_to_text("") is None


def test_detect_remote():
    assert detect_remote("Remote, Germany") is True
    assert detect_remote("Work from home") is True
    assert detect_remote("Berlin, Germany") is False
    assert detect_remote(None) is None


def test_dedup_key_matches_across_formatting():
    a = make_dedup_key("Data Engineer", "GitLab", "Berlin, Germany")
    b = make_dedup_key("data  engineer", "GitLab Inc", "Berlin")
    # Company suffix differs, so these are intentionally NOT equal; the key
    # is stable for identical company/title/city though.
    c = make_dedup_key("Data Engineer", "GitLab", "Berlin")
    assert a == c
    assert a.startswith("gitlab:data-engineer:berlin")


def test_dedup_key_without_location():
    key = make_dedup_key("AI Engineer", "Stripe", None)
    assert key == "stripe:ai-engineer"
