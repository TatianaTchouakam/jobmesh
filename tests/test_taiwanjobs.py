"""Offline test: Taiwan Jobs XML webservice (fullwidth-paren tags via regex)."""
from jobmesh.connectors.taiwanjobs import TaiwanJobsConnector, _field

_XML = """<?xml version='1.0' ?><DataList>
<Data>
<OCCU_DESC（職務名稱）><![CDATA[寬頻網路電信工程師]]></OCCU_DESC（職務名稱）>
<WK_TYPE（職務性質）><![CDATA[全職]]></WK_TYPE（職務性質）>
<CJOB_NAME1（職務大類別名稱）><![CDATA[技術／維修／操作]]></CJOB_NAME1（職務大類別名稱）>
<JOB_DETAIL（工作內容）><![CDATA[架設網路]]></JOB_DETAIL（工作內容）>
<CITYNAME（工作地點）><![CDATA[台北市信義區]]></CITYNAME（工作地點）>
<NT_L（薪資範圍下限）><![CDATA[40000]]></NT_L（薪資範圍下限）>
<NT_U（薪資範圍上限）><![CDATA[55000]]></NT_U（薪資範圍上限）>
<TRANDATE（職缺更新日期）><![CDATA[20261118]]></TRANDATE（職缺更新日期）>
<COMPNAME（公司名稱）><![CDATA[豐隆大飯店股份有限公司]]></COMPNAME（公司名稱）>
<URL_QUERY（職缺資料URL）><![CDATA[https://job.taiwanjobs.gov.tw/Internet/index/jobdata.aspx?HIRE_ID=14823857]]></URL_QUERY（職缺資料URL）>
</Data>
<Data>
<OCCU_DESC（職務名稱）><![CDATA[餐廳領檯]]></OCCU_DESC（職務名稱）>
<WK_TYPE（職務性質）><![CDATA[兼職]]></WK_TYPE（職務性質）>
<CITYNAME（工作地點）><![CDATA[高雄市]]></CITYNAME（工作地點）>
<TRANDATE（職缺更新日期）><![CDATA[20261115]]></TRANDATE（職缺更新日期）>
<COMPNAME（公司名稱）><![CDATA[某餐廳]]></COMPNAME（公司名稱）>
<URL_QUERY（職缺資料URL）><![CDATA[https://job.taiwanjobs.gov.tw/...HIRE_ID=14999999]]></URL_QUERY（職缺資料URL）>
</Data>
</DataList>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp("")  # 404/empty -> allowed
        assert "zipno=802" in url
        return _Resp(_XML)


def test_taiwanjobs_parses_fullwidth_tags():
    jobs = TaiwanJobsConnector("802", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "14823857"
    assert a.title == "寬頻網路電信工程師"
    assert a.company == "豐隆大飯店股份有限公司"
    assert a.location == "台北市信義區"
    assert a.salary == "40000–55000"
    assert a.employment_type == "Full-time"       # 全職 mapped
    assert a.source_url.endswith("HIRE_ID=14823857")
    assert a.posted_at.startswith("2026-11-18")
    assert jobs[1].employment_type == "Part-time"  # 兼職


def test_field_helper_handles_parens():
    blk = "<COMPNAME（公司名稱）><![CDATA[ACME]]></COMPNAME（公司名稱）>"
    assert _field(blk, "COMPNAME") == "ACME"
    assert _field(blk, "MISSING") is None
