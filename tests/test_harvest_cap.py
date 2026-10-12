"""A max_records cap that falls part-way through a page must not strand the
rest of that page (stress test, 12 October 2026).

OAI-PMH resumes only at page boundaries. kci_harvest cut the last page to
max_records and then offered the token for the *next* page, so the records
it had dropped could not be reached by following its own hint.
"""
import asyncio
import json

import pytest

from korea_scholarship_mcp import server as S

DC = 'xmlns:dc="http://purl.org/dc/elements/1.1/"'


def _page(first, n, token=None):
    recs = "".join(
        f"<record><header><identifier>oai:kci:{i}</identifier></header>"
        f"<metadata><dc {DC}><dc:title>t{i}</dc:title></dc></metadata></record>"
        for i in range(first, first + n))
    tok = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return ('<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>'
            f"{recs}{tok}</ListRecords></OAI-PMH>")


@pytest.fixture
def two_pages(monkeypatch):
    seen = []

    async def fake_get(url, params):
        seen.append(params.get("resumptionToken"))
        if params.get("resumptionToken") == "TOK2":
            return _page(100, 100, "TOK3"), None
        return _page(0, 100, "TOK2"), None
    monkeypatch.setattr(S, "_get", fake_get)
    return seen


def _more(env):
    return [d for d in env["diagnostics"] if d["code"] == "OAI_MORE_AVAILABLE"]


def test_cap_inside_first_page_does_not_offer_the_next_page(two_pages):
    env = json.loads(asyncio.run(S.kci_harvest("2026-07-01", "2026-07-02", max_records=1)))
    assert env["result"]["returned"] == 1
    (d,) = _more(env)
    assert "TOK2" not in d["hint"], "TOK2 starts after the 99 records that were dropped"
    assert "99" in d["message"] and "100" in d["hint"]


def test_cap_inside_a_later_page_offers_the_token_that_fetched_it(two_pages):
    env = json.loads(asyncio.run(S.kci_harvest("2026-07-01", "2026-07-02", max_records=150)))
    assert env["result"]["returned"] == 150
    (d,) = _more(env)
    assert "resumption_token='TOK2'" in d["hint"] and "TOK3" not in d["hint"]
    assert "50" in d["message"] and "50" in d["hint"]


def test_cap_on_a_page_boundary_offers_the_next_token(two_pages):
    env = json.loads(asyncio.run(S.kci_harvest("2026-07-01", "2026-07-02", max_records=100)))
    assert env["result"]["returned"] == 100
    (d,) = _more(env)
    assert "resumption_token='TOK2'" in d["hint"]
