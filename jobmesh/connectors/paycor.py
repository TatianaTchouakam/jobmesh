"""Paycor connector — public per-client ATOM job feed (Paycor Recruiting, ex-Newton).

Paycor Recruiting (formerly Newton Software, now part of Paychex) lets each
customer publish its open jobs as a public ATOM feed, documented by Paycor for
the "Use an iFrame and ATOM Feed" careers-page option. There is no central
feed: each employer has its own, identified by its ``clientId``. Each <entry>
carries standard ATOM fields plus ``newton:`` namespaced fields:

    <entry>
      <title>Warehouse Associate</title>
      <link href="https://recruitingbypaycor.com/career/JobIntroduction.action?clientId=...&amp;id=..."/>
      <id>8a7883d0...</id>
      <updated>2026-11-20T14:02:11Z</updated>
      <summary type="html">&lt;p&gt;...&lt;/p&gt;</summary>
      <newton:jobid>WH-102</newton:jobid>
      <newton:department>Operations</newton:department>
      <newton:location>Cincinnati</newton:location>
      <newton:state>OH</newton:state>
      <newton:country>United States</newton:country>
    </entry>

``board`` is "clientId|Company" (the company name is not in the feed). The
feed URL is read from the employer's public careers page when it declares one
(``<link rel="alternate" type="application/atom+xml">``), otherwise the
documented hosts are tried in order. robots.txt is honoured on every host;
no key, no cookie, no session token is used. Every job links back to the
employer's own posting.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
MAX_JOBS = 1000

HOSTS = ("https://recruitingbypaycor.com", "https://newton.newtonsoftware.com")
CAREER_HOME = "{host}/career/CareerHome.action?clientId={cid}"
ATOM_PATHS = ("{host}/career/CareerAtomFeed.action?clientId={cid}",)

_ENTRY = re.compile(r"<entry\b[^>]*>(.*?)</entry>", re.IGNORECASE | re.DOTALL)
_ALT = re.compile(
    r"<link\b[^>]*type=[\"']application/atom\+xml[\"'][^>]*>", re.IGNORECASE)
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", val, re.DOTALL)
    if cd:
        val = cd.group(1).strip()
    return html.unescape(val) if val else None


def _link(block: str) -> str | None:
    for m in re.finditer(r"<link\b([^>]*)/?>", block, re.IGNORECASE):
        attrs = m.group(1)
        rel = re.search(r"rel=[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
        if rel and rel.group(1).lower() not in ("alternate", ""):
            continue
        href = _HREF.search(attrs)
        if href:
            return html.unescape(href.group(1))
    return None


def parse_atom(text: str, platform: str, board: str, company: str) -> list[Job]:
    at = now_iso()
    jobs: list[Job] = []
    seen: set[str] = set()
    for block in _ENTRY.findall(text):
        link = _link(block)
        ref = _tag(block, "id") or _tag(block, "newton:jobid") or link
        if not ref or ref in seen:
            continue
        seen.add(ref)
        title = _tag(block, "title") or "(untitled)"
        city = _tag(block, "newton:location") or _tag(block, "name")
        state = _tag(block, "newton:state")
        country = _tag(block, "newton:country")
        loc = ", ".join(p for p in (city, state, country) if p) or None
        dept = _tag(block, "newton:department") or _tag(block, "category")
        desc = _tag(block, "summary") or _tag(block, "content")
        jobs.append(Job(
            source_platform=platform,
            source_board=board,
            source_job_id=str(ref),
            title=title,
            company=company,
            location=loc,
            description=html_to_text(desc) if desc else None,
            source_url=link,
            apply_url=link,
            category=dept,
            remote=detect_remote(f"{loc or ''} {title}"),
            posted_at=_tag(block, "published") or _tag(block, "updated"),
            dedup_key=make_dedup_key(title, company, loc),
            first_seen=at,
            last_checked=at,
            is_open=True,
        ))
        if len(jobs) >= MAX_JOBS:
            break
    return jobs


class PaycorConnector(Connector):
    platform = "paycor"

    def __init__(self, board: str, session: requests.Session | None = None):
        cid, _, company = board.partition("|")
        super().__init__(cid.strip())
        self._company = company.strip() or "Paycor employer"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _declared_feed(self, host: str) -> str | None:
        """The ATOM URL the employer's own careers page declares, if any."""
        page = CAREER_HOME.format(host=host, cid=self.board)
        if not robots_allowed(page, self._session):
            return None
        try:
            r = self._session.get(page, timeout=TIMEOUT)
        except requests.RequestException:
            return None
        if r.status_code >= 400:
            return None
        m = _ALT.search(r.text or "")
        if not m:
            return None
        href = _HREF.search(m.group(0))
        return urljoin(page, html.unescape(href.group(1))) if href else None

    def feed_urls(self) -> list[str]:
        urls: list[str] = []
        for host in HOSTS:
            declared = self._declared_feed(host)
            if declared:
                urls.append(declared)
            urls.extend(p.format(host=host, cid=self.board) for p in ATOM_PATHS)
        return list(dict.fromkeys(urls))

    def fetch(self) -> list[Job]:
        last_error: Exception | None = None
        for url in self.feed_urls():
            if not robots_allowed(url, self._session):
                continue
            try:
                r = self._session.get(url, timeout=TIMEOUT)
                r.raise_for_status()
            except requests.RequestException as exc:
                last_error = exc
                continue
            if "<feed" not in (r.text or "")[:2000]:
                continue
            return parse_atom(r.text, self.platform, self.board, self._company)
        if last_error:
            raise last_error
        raise RuntimeError(f"no public ATOM feed found for Paycor client {self.board}")
