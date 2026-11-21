"""Offline test: HERP list page -> per-job schema.org JSON-LD."""
from jobmesh.connectors.herp import HerpConnector

_LIST = """<html><body>
<a href="/v1/herpinc/9tYFbxcUPSEP">Engineer</a>
<a href="/v1/herpinc/6kOgdGmAe5Ao">Designer</a>
<a href="/v1/herpinc/requisition-groups/64654cdc-54c0-43a2-a690-14cdc5d98763">Group</a>
<a href="/ref/foo">ref</a>
</body></html>"""

def _detail(title, loc):
    return ('<html><head><script type="application/ld+json">'
            '{"@context":"https://schema.org/","@type":"JobPosting",'
            f'"title":"{title}","description":"<p>Role</p>",'
            '"datePosted":"2026-11-10T00:00:00.000Z",'
            '"hiringOrganization":{"@type":"Organization","name":"HERP Inc."},'
            f'"jobLocation":{{"@type":"Place","address":"{loc}"}}}}'
            '</script></head><body>x</body></html>')


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp("User-agent: *\nDisallow: /ref/\nDisallow: /apply$\n")
        if url == "https://herp.careers/v1/herpinc":
            return _Resp(_LIST)
        if url.endswith("9tYFbxcUPSEP"):
            return _Resp(_detail("Backend Engineer", "Tokyo"))
        if url.endswith("6kOgdGmAe5Ao"):
            return _Resp(_detail("Product Designer", "Remote Japan"))
        raise AssertionError("unexpected url " + url)


def test_herp_list_and_jsonld():
    jobs = HerpConnector("herpinc", session=_Session()).fetch()
    assert len(jobs) == 2                       # 2 jobs; group + ref link skipped
    ids = {j.source_job_id for j in jobs}
    assert ids == {"9tYFbxcUPSEP", "6kOgdGmAe5Ao"}
    a = next(j for j in jobs if j.source_job_id == "9tYFbxcUPSEP")
    assert a.title == "Backend Engineer"
    assert a.company == "HERP Inc."
    assert a.location == "Tokyo"
    assert a.source_url == "https://herp.careers/v1/herpinc/9tYFbxcUPSEP"
    assert a.posted_at.startswith("2026-11-10")
