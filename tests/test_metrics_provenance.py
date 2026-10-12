"""kci_journal_metrics records the term it sent (stress test, 12 October
2026): given both a journal name and a journal_id it queried by id only, but
the envelope and the receipt hash named the journal."""
import asyncio
import json

import pytest

from korea_scholarship_mcp import server as S

EMPTY = "<MetaData><outputData><result><total>0</total></result></outputData></MetaData>"


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake_get(url, params):
        calls.append(dict(params))
        return EMPTY, None
    monkeypatch.setattr(S, "_get", fake_get)
    monkeypatch.setattr(S, "KCI_API_KEY", "dummy")
    return calls


def test_id_lookup_records_the_id(sent):
    env = json.loads(asyncio.run(S.kci_journal_metrics(journal="은행법연구", journal_id="JOUR123")))
    assert sent[0].get("id") == "JOUR123" and "journal" not in sent[0]
    assert env["query"]["input_terms"] == "JOUR123"
    assert env["query"]["normalized"] == "JOUR123"


def test_name_lookup_records_the_name(sent):
    env = json.loads(asyncio.run(S.kci_journal_metrics(journal="은행법연구")))
    assert sent[0].get("journal") == "은행법연구"
    assert env["query"]["normalized"] == "은행법연구"
