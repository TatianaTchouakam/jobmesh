"""Taiwan Jobs connector — Ministry of Labor public job webservice.

Taiwan's public employment service (taiwanjobs.gov.tw) exposes a keyless XML
webservice, published under the Open Government Data License 1.0:

    GET https://free.taiwanjobs.gov.tw/webservice_taipei/Webservice.ashx
        ?zipno={postalCode}&count=1000
    -> <DataList><Data>
         <OCCU_DESC（職務名稱）>title</OCCU_DESC（職務名稱）>
         <COMPNAME（公司名稱）>company</COMPNAME（公司名稱）>
         <CITYNAME（工作地點）>location</CITYNAME（工作地點）>
         <WK_TYPE（職務性質）>全職</WK_TYPE（職務性質）>
         <TRANDATE（職缺更新日期）>20261118</TRANDATE（職缺更新日期）>
         <URL_QUERY（職缺資料URL）>https://job.taiwanjobs.gov.tw/...HIRE_ID=...</URL_QUERY…>
       </Data>...</DataList>

The tag names embed fullwidth Chinese parentheses, which a strict XML parser
rejects, so fields are read by regex on the tag prefix. robots.txt is absent
(404) — nothing disallowed. No key. ``board`` is a postal code (zipno), e.g.
"802" (Kaohsiung); several cities together give national coverage.
"""

from __future__ import annotations

import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key, normalize_date
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
COUNT = 1000
API = "https://free.taiwanjobs.gov.tw/webservice_taipei/Webservice.ashx"

_RECORD = re.compile(r"<Data>(.*?)</Data>", re.IGNORECASE | re.DOTALL)
_HIRE_ID = re.compile(r"HIRE_ID=(\d+)")
_EMP = {"全職": "Full-time", "兼職": "Part-time", "計時": "Part-time", "臨時": "Temporary"}


def _field(block: str, prefix: str) -> str | None:
    # tag looks like <PREFIX（中文）> ... </PREFIX（中文）>
    m = re.search(rf"<{prefix}[^>]*>(.*?)</{prefix}[^>]*>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", val, re.DOTALL)
    if cd:
        val = cd.group(1).strip()
    return val or None


def _salary(lo: str | None, hi: str | None) -> str | None:
    lo, hi = (lo or "").strip(), (hi or "").strip()
    if lo and hi and lo != "0":
        return f"{lo}–{hi}" if lo != hi else lo
    return (lo if lo and lo != "0" else None) or (hi if hi and hi != "0" else None)


class TaiwanJobsConnector(Connector):
    platform = "taiwanjobs"

    def __init__(self, board: str = "100", session: requests.Session | None = None):
        super().__init__(str(board))
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        url = f"{API}?zipno={self.board}&count={COUNT}"
        if not robots_allowed(url, self._session):
            return []
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for block in _RECORD.findall(resp.text):
            title = _field(block, "OCCU_DESC")
            if not title:
                continue
            url_q = _field(block, "URL_QUERY")
            m = _HIRE_ID.search(url_q or "")
            jid = m.group(1) if m else make_dedup_key(title, _field(block, "COMPNAME") or "", self.board)
            if not jid or jid in seen:
                continue
            seen.add(jid)
            company = _field(block, "COMPNAME") or "台灣就業通"
            location = _field(block, "CITYNAME")
            wk = _field(block, "WK_TYPE")
            desc = _field(block, "JOB_DETAIL")
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=company,
                location=location,
                description=html_to_text(desc) if desc else None,
                source_url=url_q,
                apply_url=url_q,
                salary=_salary(_field(block, "NT_L"), _field(block, "NT_U")),
                employment_type=_EMP.get(wk, wk),
                category=_field(block, "CJOB_NAME1"),
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=normalize_date(_field(block, "TRANDATE")),
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
