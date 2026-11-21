"""Offline test: JobBoard.com per-sector RSS (retry + dedup across sectors)."""
import jobmesh.connectors.jobboardcom as _jb
_jb.time.sleep = lambda *a, **k: None
from jobmesh.connectors.jobboardcom import JobBoardComConnector

_CHALLENGE = "<html><head><script>setTimeout('location.reload()')</script></head></html>"

def _feed(*titles):
    items = "".join(
        f"<item><title>{t}</title>"
        f"<link>https://preview.jobboard.com/jobs/{t.lower().replace(' ','-')}-{i}</link>"
        f"<description><![CDATA[Great job]]></description>"
        f"<pubDate>Sat, 21 Nov 2026 17:43:00 GMT</pubDate></item>"
        for i, t in enumerate(titles))
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'


class _Resp:
    def __init__(self, text, status=200): self.text = text; self.status_code = status
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.calls = 0
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /Scripts/\n")
        self.calls += 1
        if "SectorIds%3d1" in url or "SectorIds=1" in url:
            # sector 1: first call 503 (challenge), retry 200
            if self.calls <= 1:
                return _Resp(_CHALLENGE, 503)
            return _Resp(_feed("Loan Clerk", "Remote Nurse"))
        if "SectorIds%3d2" in url or "SectorIds=2" in url:
            return _Resp(_feed("Loan Clerk", "CFO"))          # "Loan Clerk" dup across sectors
        return _Resp('<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>')  # empty sector


def test_jobboardcom_retries_and_dedups():
    s = _Session()
    jobs = JobBoardComConnector("preview.jobboard.com", session=s).fetch()
    titles = [j.title for j in jobs]
    assert "Loan Clerk" in titles and "Remote Nurse" in titles and "CFO" in titles
    # "Loan Clerk" appears in sectors 1 and 2 but is deduped by link slug
    assert titles.count("Loan Clerk") == 1
    a = [j for j in jobs if j.title == "Remote Nurse"][0]
    assert a.company == "JobBoard.com"
    assert a.remote is True
    assert a.source_url.startswith("https://preview.jobboard.com/jobs/")
