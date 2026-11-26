"""Oracle board parsing: site is optional (the public CE API works without it)."""
from jobmesh.connectors.oracle import OracleConnector


def test_host_only_board():
    c = OracleConnector("ejwl.fa.us2.oraclecloud.com")
    assert c.host == "ejwl.fa.us2.oraclecloud.com" and c.site == ""


def test_host_site_board():
    c = OracleConnector("ejwl.fa.us2.oraclecloud.com:CX:Marriott")
    assert c.host == "ejwl.fa.us2.oraclecloud.com" and c.site == "CX" and c.company == "Marriott"
