"""ADP connector — offline: public Career Center job-requisitions feed."""
from jobmesh.connectors.adp import AdpConnector

FEED = {"jobRequisitions": [
    {"itemID": "9202914658560_1", "clientRequisitionID": "1437",
     "requisitionTitle": "Service Engineer",
     "requisitionLocations": [{"nameCode": {"shortName": " Indianapolis, IN, US"},
                               "address": {"cityName": "Indianapolis",
                                           "countrySubdivisionLevel1": {"codeValue": "IN"}}}],
     "workLevelCode": {"shortName": "Full Time"}, "postDate": "2026-11-04T08:19:00"},
    {"itemID": "9202912072177_2", "requisitionTitle": "Assembler",
     "requisitionLocations": [{"address": {"cityName": "Grand Rapids",
                                           "countrySubdivisionLevel1": {"codeValue": "MI"}}}],
     "workLevelCode": {"shortName": "Part Time"}, "postDate": "2026-11-05T00:00:00"},
], "meta": {"totalNumber": 2}}


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self):
        self.headers = {}

    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)
        return _Resp(FEED)


def test_career_center_feed_maps():
    c = AdpConnector("e9311e7a|22330316_1091|Hurco", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    a = j["9202914658560_1"]
    assert a.title == "Service Engineer"
    assert a.company == "Hurco"
    assert a.location == "Indianapolis, IN, US"
    assert "jobId=9202914658560_1" in a.apply_url
    assert j["9202912072177_2"].location == "Grand Rapids, MI"
