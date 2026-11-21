"""Avature connector — offline, against the real RSS feed markup."""
from jobmesh.connectors.avature import AvatureConnector

ROBOTS = "User-agent: *\nAllow: /careers\nAllow: /*/careers\nDisallow: /*/careers/*qtvc=\n"


def _item(jid, title):
    return (f"<item><title><![CDATA[{title}]]></title>"
            f"<description><![CDATA[ - {jid}]]></description>"
            f'<guid isPermaLink="true">https://delta.avature.net/careers/JobDetail/{title.replace(" ", "-")}/{jid}</guid>'
            f"<link>https://delta.avature.net/careers/JobDetail/{title.replace(' ', '-')}/{jid}</link>"
            f"<pubDate>Fri, 18 Aug 2023 00:00:00 +0000</pubDate></item>")


def _feed(items):
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            '<title>careers</title>' + "".join(items) + "</channel></rss>")


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _FakeSession:
    def __init__(self, feed, robots=ROBOTS):
        self.headers = {}
        self._feed = feed
        self._robots = robots

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(self._robots)
        if url.endswith("/feed/"):
            return _Resp(self._feed)
        return _Resp("", status=404)


def test_parses_rss():
    feed = _feed([_item("33793", "Flight Attendant"),
                  _item("40001", "Remote Software Engineer")])
    c = AvatureConnector("delta", session=_FakeSession(feed))
    jobs = c.fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.title == "Flight Attendant"
    assert a.company == "Delta"
    assert a.source_job_id == "33793"
    assert a.source_url == "https://delta.avature.net/careers/JobDetail/Flight-Attendant/33793"
    assert a.posted_at.startswith("2023-08-18")  # normalized to ISO
    assert a.source_platform == "avature" and a.source_board == "delta"
    assert jobs[1].remote is True        # "Remote ..." in title


def test_robots_blocks():
    feed = _feed([_item("1", "X")])
    c = AvatureConnector("blocked-av", session=_FakeSession(feed, robots="User-agent: *\nDisallow: /\n"))
    assert c.fetch() == []
