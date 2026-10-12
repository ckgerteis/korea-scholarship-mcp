"""A 200 that is well-formed XML but not the protocol is an error, not zero.

Stress test, 12 October 2026: an HTML maintenance page, a bare <MetaData/>, or
an OAI-PMH response with no ListRecords, served with status 200, came back
from every data tool with total 0 and no error: kci_search said
ZERO_CONJUNCTION, kci_article and oak_record said OK, the harvests said zero
records, and korea_sources_status called all three sources accepted.
"""
import asyncio
import json
from pathlib import Path

import pytest

from korea_scholarship_mcp import server as S

OAK = (Path(__file__).parent / "fixtures" / "oak_listrecords.xml").read_text(encoding="utf-8")
HTML = "<html><body><h1>Service temporarily unavailable</h1></body></html>"
OAI_NS = "http://www.openarchives.org/OAI/2.0/"


@pytest.fixture
def body(monkeypatch):
    box = {}

    async def fake_get(url, params):
        return box["body"], None
    monkeypatch.setattr(S, "_get", fake_get)
    monkeypatch.setattr(S, "KCI_API_KEY", "dummy")
    return box


def _codes(out):
    env = json.loads(out)
    return env, [d["code"] for d in env["diagnostics"]]


@pytest.mark.parametrize("bad", [HTML, "<MetaData/>", "<MetaData><inputData/></MetaData>"])
def test_kci_rest_wrong_shape_is_parse_error(body, bad):
    body["body"] = bad
    env, codes = _codes(asyncio.run(S.kci_search("여성")))
    assert "PARSE_ERROR" in codes and "ZERO_CONJUNCTION" not in codes
    env, codes = _codes(asyncio.run(S.kci_article("ART001995054")))
    assert "PARSE_ERROR" in codes and "OK" not in codes


NOT_OAI = [
    HTML,
    "<MetaData/>",
    f'<OAI-PMH xmlns="{OAI_NS}"><responseDate>2026-10-12</responseDate></OAI-PMH>',
    '<OAI-PMH><ListRecords/></OAI-PMH>',  # namespace stripped
]


@pytest.mark.parametrize("bad", NOT_OAI)
def test_oai_wrong_shape_is_parse_error(body, bad):
    body["body"] = bad
    for call in (lambda: S.kci_harvest("2024-01-01", "2024-01-31"),
                 lambda: S.oak_harvest("2024-01-01", "2024-01-31"),
                 lambda: S.oak_record("16974253")):
        env, codes = _codes(asyncio.run(call()))
        assert "PARSE_ERROR" in codes, codes
        assert "OK" not in codes and env["result"]["total"] == 0


def test_status_does_not_call_a_garbage_page_accepted(body):
    body["body"] = HTML
    out = json.loads(asyncio.run(S.korea_sources_status()))
    rows = out["checks"]
    assert not any(r.get("accepted") for r in rows), rows


def test_real_oak_page_still_harvests(body):
    body["body"] = OAK
    env, codes = _codes(asyncio.run(S.oak_harvest("2024-01-01", "2024-01-31")))
    assert "PARSE_ERROR" not in codes and env["result"]["returned"] > 0


def test_oai_no_records_match_is_still_info(body):
    body["body"] = (f'<OAI-PMH xmlns="{OAI_NS}"><responseDate>2026-10-12</responseDate>'
                    '<error code="noRecordsMatch">none</error></OAI-PMH>')
    _, codes = _codes(asyncio.run(S.oak_harvest("2024-01-01", "2024-01-31")))
    assert "OAI_NO_RECORDS" in codes and "PARSE_ERROR" not in codes
