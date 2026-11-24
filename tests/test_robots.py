"""Robots enforcement regression tests — the core integrity guarantee.

These pin the decisions that must never silently flip (e.g. after a urllib
internals change between Python versions): a blanket Disallow must block, and
the Disallow:/ + Allow:/careers/ longest-match pattern must still expose the
public career pages while blocking the rest.
"""

from jobmesh import robots as R


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _Session:
    def __init__(self, robots_txt, status=200):
        self.headers = {}
        self._robots, self._status = robots_txt, status

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(self._robots, self._status)
        return _Resp("", 404)


def test_star_disallow_all_blocks():
    R._cache.clear()
    s = _Session("User-agent: *\nDisallow: /\n")
    assert R.allowed("https://x.example.com/jobs/1", s) is False


def test_named_agent_disallow_blocks():
    R._cache.clear()
    s = _Session("User-agent: JobmeshBot\nDisallow: /\n")
    assert R.allowed("https://x.example.com/jobs/1", s) is False


def test_longest_match_allow_careers():
    R._cache.clear()
    txt = "User-agent: *\nDisallow: /\nAllow: /careers/\n"
    assert R.allowed("https://x.example.com/careers/42", _Session(txt)) is True
    R._cache.clear()
    assert R.allowed("https://x.example.com/private", _Session(txt)) is False


def test_missing_robots_allows():
    R._cache.clear()
    s = _Session("", status=404)
    assert R.allowed("https://x.example.com/jobs/1", s) is True
