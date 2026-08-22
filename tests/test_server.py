"""Tests for korea-scholarship-mcp.

Offline tests run against fixtures captured from the live services on
19 Aug 2026. The live tests are marked and skipped unless RUN_LIVE=1, so the
suite stays deterministic; run them when a service contract may have shifted.

    python -m pytest tests -q
    RUN_LIVE=1 python -m pytest tests -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from korea_scholarship_mcp import mediation as M  # noqa: E402
from korea_scholarship_mcp import server as S  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = os.environ.get("RUN_LIVE") == "1"
# OAK is unreachable from some networks (including the build sandbox), and a
# test that cannot reach its service must not pass quietly. Gate it separately
# so RUN_LIVE=1 stays green where only OAK is blocked, and set RUN_LIVE_OAK=1
# from a network that can reach oak.go.kr.
LIVE_OAK = os.environ.get("RUN_LIVE_OAK") == "1"


# ---------------------------------------------------------------- script ----


def test_hangul_is_not_latin():
    """The regression that motivated the 2.1.0 fork of mediation.py: the
    Japanese copy classifies Hangul as 'latin' and fires the romanisation
    warning on every correct Korean query."""
    assert M.detect_script("여성노동") == "hangul"
    assert M.detect_script("한국") == "hangul"


def test_script_classification():
    assert M.detect_script("women's labour") == "latin"
    assert M.detect_script("") == "latin"
    assert M.detect_script("동곡서첩") == "hangul"
    assert M.detect_script("筆寫本") == "han"
    assert M.detect_script("國土硏究院 연구") == "han_hangul"
    assert M.detect_script("Korea 연구") == "mixed"
    assert M.detect_script("女性労働") == "han"       # kanji-only Japanese
    assert M.detect_script("じょせい") == "kana"


def test_script_diag_fires_only_on_latin():
    assert S._script_diags("여성", "KCI") == []
    assert S._script_diags("", "KCI") == []
    d = S._script_diags("yeoseong", "KCI")
    assert d and d[0]["code"] == "SCRIPT_LATIN_QUERY"


# ------------------------------------------------------------- redaction ----


def test_key_is_redacted_from_messages(monkeypatch):
    """Both branches, separately. The URL form is caught by the regex; a bare
    key echoed in a body is caught only by the literal replacement. The earlier
    version used one fixture containing `key=…&`, so deleting the literal
    branch entirely left the suite green."""
    monkeypatch.setattr(S, "KCI_API_KEY", "SECRETKEY123")

    url_form = "GET https://open.kci.go.kr/…/openApiSearch.kci?key=SECRETKEY123&apiCode=x failed"
    out = S._redact(url_form)
    assert "SECRETKEY123" not in out and "REDACTED" in out

    # bare key, no query-string delimiter anywhere — regex cannot help here
    bare = "<inputData><key>SECRETKEY123</key></inputData>"
    out = S._redact(bare)
    assert "SECRETKEY123" not in out, "the literal-key branch is not doing its job"

    # and the regex must still work when the configured key is unknown
    monkeypatch.setattr(S, "KCI_API_KEY", "")
    assert "OTHERKEY" not in S._redact("…?key=OTHERKEY&apiCode=x")


def test_key_never_reaches_the_receipt():
    params = {"key": "SECRETKEY123", "apiCode": "articleSearch", "title": "여성", "author": ""}
    safe = S._safe_params(params)
    assert "key" not in safe and "apiCode" not in safe
    assert safe == {"title": "여성"}


# ------------------------------------------------------------------ OAK ----


def _oak_records():
    from defusedxml import ElementTree as DET

    root = DET.fromstring((FIXTURES / "oak_listrecords.xml").read_bytes())
    return [r for r in root.iter() if S._ln(r) == "record"]


def test_oak_nonstandard_fields_are_read():
    """OAK emits dc:title_h, not dc:title. A parser written to the Dublin Core
    spec returns empty records against it."""
    items = [S._oak_item(r) for r in _oak_records()]
    assert len(items) == 3
    assert items[0]["title"]["ko"] == "부산·진해 경제자유구역 개발계획.제2권 :부문별 계획"
    assert items[0]["ids"]["oai_id"] == "oai:oak.go.kr:16974253"
    assert items[0]["ids"]["fulltext_url"].endswith("39899")
    assert items[0]["source"]["holding_org"] == "국토연구원"


def test_oak_repeated_authors_and_year_extraction():
    items = [S._oak_item(r) for r in _oak_records()]
    names = [a["name"] for a in items[1]["authors"]]
    assert names == ["김상조", "김성수", "김동근"]      # leading spaces stripped
    assert items[1]["source"]["year"] == 2013            # from "2013-12-29"
    assert items[0]["source"]["year"] == 2004            # from bare "2004"
    assert items[1]["ids"]["issn"] == "1229-8638"


def test_oak_material_type_from_keyword():
    items = [S._oak_item(r) for r in _oak_records()]
    assert [i["record_type"] for i in items] == ["report", "book", "book"]
    assert items[2]["extra"]["material_type"] == ["OldBook"]


def test_oak_hanja_title_is_not_mistaken_for_english():
    """고서 records carry Hanja titles. Script detection must not route them to
    the English slot, and must not route the Hanja publisher there either."""
    items = [S._oak_item(r) for r in _oak_records()]
    assert items[2]["title"]["ko"] == "동곡서첩"
    assert items[2]["title"]["en"] is None
    assert items[2]["extra"]["abstract_en"] == "筆寫本."


# ------------------------------------------------------------------ KCI ----


def test_kci_oai_untyped_identifiers_fall_back_to_patterns():
    """Fallback path only. KCI in fact types every identifier (see the live test
    below); this fixture is the degraded case, and pattern matching is what
    remains when the type attribute is absent."""
    from defusedxml import ElementTree as DET

    xml = """<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
    <ListRecords><record>
      <header><identifier>oai:kci.go.kr:ARTI/484375</identifier><datestamp>2026-07-02</datestamp></header>
      <metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                           xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>IT보안과 인터넷뱅킹</dc:title>
        <dc:title>IT-security and internet banking</dc:title>
        <dc:creator>스기우라 노부히코(주오대학교); 이현정(충남대학교)</dc:creator>
        <dc:subject>사회과학일반</dc:subject>
        <dc:identifier>은행법연구, 8(1), 15, pp.17-28</dc:identifier>
        <dc:identifier>ART001995054</dc:identifier>
        <dc:identifier>0</dc:identifier>
        <dc:identifier>G704-SER000010547.2015.8.1.001</dc:identifier>
        <dc:identifier>N</dc:identifier>
        <dc:publisher>은행법학회</dc:publisher>
        <dc:date>2015-05</dc:date>
        <dc:language>한국어</dc:language>
        <dc:rights>Y</dc:rights>
      </oai_dc:dc></metadata>
    </record></ListRecords></OAI-PMH>"""
    rec = [r for r in DET.fromstring(xml.encode()).iter() if S._ln(r) == "record"][0]
    it = S._kci_oai_item(rec)
    assert it["ids"]["kci_id"] == "ART001995054"
    assert it["ids"]["uci"].startswith("G704")
    assert it["title"]["ko"].startswith("IT보안과")
    assert it["title"]["en"] == "IT-security and internet banking"
    assert it["source"]["journal_ko"] == "은행법연구"
    assert it["source"]["volume"] == "8"
    assert it["source"]["issue"] == "1"
    assert it["source"]["pages"] == "17-28"
    assert it["source"]["year"] == 2015
    assert [a["name"] for a in it["authors"]] == ["스기우라 노부히코", "이현정"]
    assert it["authors"][1]["affiliation"] == "충남대학교"


def test_kci_rest_error_is_read_from_the_body(monkeypatch):
    """KCI answers HTTP 200 on failure and puts the error in resultMsg, so a
    status-code check alone reports an unregistered key as success."""
    body = """<?xml version="1.0" encoding="UTF-8"?>
    <MetaData><inputData><key>00000001</key></inputData>
    <outputData><result><resultMsg>등록되지 않은 key 입니다.</resultMsg></result></outputData></MetaData>"""

    async def fake_get(url, params):
        return body, None

    monkeypatch.setattr(S, "_get", fake_get)
    monkeypatch.setattr(S, "KCI_API_KEY", "dummy")

    import asyncio

    root, err = asyncio.run(S._kci_rest("articleSearch", {"title": "여성"}))
    assert root is None
    assert err["code"] == "KCI_REJECTED"
    assert "등록되지 않은" in err["message"]


def test_client_filter_covers_title_author_and_org():
    """`contains` is the only query mechanism the harvest tools have. The
    earlier test matched on holding organisation alone, so deleting title and
    author matching from the haystack left the suite green."""
    items = [S._oak_item(r) for r in _oak_records()]

    by_org = S._filter(items, "국토연구원")
    assert len(by_org) == 2
    assert all(i["matched_in"] == "client_filter" for i in by_org)

    by_title = S._filter(items, "동곡서첩")
    assert len(by_title) == 1 and by_title[0]["title"]["ko"] == "동곡서첩"

    by_author = S._filter(items, "김동근")
    assert len(by_author) == 1 and "김동근" in [a["name"] for a in by_author[0]["authors"]]

    assert S._filter(items, "존재하지않는문자열") == []


# --------------------------------------------------------------- envelope ----


def test_envelope_shape_and_breadth():
    env = M.build_envelope(
        server="korea_scholarship_mcp",
        operation="t",
        input_terms="여성",
        normalized="여성",
        params={"a": 1},
        matching_mode="metadata_conjunction",
        total=300,
        start=0,
        items=[M.make_item(title_ko="제목", kci_id="ART1")],
        diagnostics=[],
        attribution="x",
    )
    assert env["query"]["script"] == "hangul"
    assert env["result"]["breadth"] == "broad"
    assert env["schema_version"] == "2.3.0"
    assert env["receipt"]["result_ids"] == ["ART1"]
    assert env["diagnostics"][0]["code"] == "OK"


def test_mediation_is_the_reconciled_union():
    """Two files both called 2.1.0 — one with emit(), one with Hangul — is what
    2.2.0 existed to end. Both capabilities must be present in the same file,
    whatever the version has since moved to. 2.3.0 adds deposit reporting on
    top; the union guarantee is what this test holds."""
    assert M.SCHEMA_VERSION == "2.3.0"
    assert hasattr(M, "emit") and hasattr(M, "ledger_available")
    assert hasattr(M, "deposit_enabled")
    assert M.detect_script("여성") == "hangul"
    assert M.detect_script("\U00020000") == "han"
    assert M.ledger_available(), "ledger.py must be vendored beside mediation.py"


def test_romanized_slot_is_never_invented():
    it = M.make_item(title_ko="여성노동")
    assert it["title"]["romanized"] is None


# ------------------------------------------------------------------ live ----


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 to exercise the network")
def test_live_kci_oai_window_returns_older_publications():
    """Guards the claim in the README: the OAI datestamp is an ingest date, so
    an old window still yields much older publications. If this ever fails, the
    'no query interface' framing in the docs needs revisiting, not the code."""
    import asyncio
    import json

    out = json.loads(asyncio.run(S.kci_harvest("2019-05-01", "2019-05-02", max_records=100)))
    years = [i["source"]["year"] for i in out["items"] if i["source"]["year"]]
    assert years and min(years) < 2018
    assert any(d["code"] == "INGEST_DATE_NOT_PUBLICATION_DATE" for d in out["diagnostics"])


@pytest.mark.skipif(not LIVE_OAK, reason="set RUN_LIVE_OAK=1 from a network that reaches oak.go.kr")
def test_live_oak_cap_is_reported():
    """OAK sends no resumptionToken; a full window must be flagged, not served
    as if complete.

    The earlier version wrapped its only assertion in `if total >= 99`, so when
    OAK was unreachable — as it is from the build sandbox — the body never ran
    and the test reported success. Now an unreachable OAK fails loudly instead
    of passing quietly."""
    import asyncio
    import json

    out = json.loads(asyncio.run(S.oak_harvest("2024-01-01", "2024-01-31")))
    codes = [d["code"] for d in out["diagnostics"]]
    assert "TRANSPORT_ERROR" not in codes, (
        "OAK was unreachable, so this test proved nothing. Run it from a network "
        "that can reach oak.go.kr.")
    assert out["result"]["total"] >= 99, "expected a full window for this month"
    assert "OAI_WINDOW_TRUNCATED" in codes


# ---------------------------------------------------------------- logging ----


def test_http_logging_is_silenced():
    """httpx logs the full request URL at INFO, and the KCI key rides in the
    query string — an unmuted logger writes the credential to the transcript.
    A stdio server also cannot afford a stdout handler."""
    import logging
    import sys

    assert logging.getLogger("httpx").level >= logging.WARNING
    assert not logging.getLogger("httpx").propagate
    assert all(
        getattr(h, "stream", None) is not sys.stdout
        for h in logging.getLogger().handlers
    )


# ------------------------------------------------- regressions from the audit --
#
# Every test below pins a defect found in the 19 Aug 2026 cross-check. Each one
# fails against the code as it stood that morning.


def _kci_rest_record(xml: str):
    from defusedxml import ElementTree as DET

    return [r for r in DET.fromstring(xml.encode()).iter() if S._ln(r) == "record"][0]


def test_pages_never_renders_the_string_none():
    """f'{fpage}-{lpage}' produced '17-None' for start-page-only records, and
    that string went straight into a citation."""
    assert S._pages("17", "28") == "17-28"
    assert S._pages("17", None) == "17"
    assert S._pages(None, "28") == "28"
    assert S._pages(None, None) is None

    it = S._kci_record_to_item(_kci_rest_record("""
    <MetaData><outputData><record><articleInfo article-id="ART1">
      <title-group><article-title lang="original">제목</article-title></title-group>
      <fpage>17</fpage></articleInfo></record></outputData></MetaData>"""))
    assert it["source"]["pages"] == "17"


def test_rest_fields_do_not_leak_across_nested_records():
    """Descendant-wide lookups assembled one item out of two works. Fields must
    come from the record's own journalInfo / articleInfo subtree."""
    it = S._kci_record_to_item(_kci_rest_record("""
    <MetaData><outputData><record>
      <journalInfo><journal-name>한국사연구</journal-name>
        <publisher-name>한국사연구회</publisher-name>
        <pub-year>2020</pub-year>
        <foreign-listed><name>SCOPUS</name></foreign-listed></journalInfo>
      <articleInfo article-id="ART_MAIN">
        <title-group><article-title lang="original">본문</article-title></title-group>
        <citation-count kci="12" wos="3"/>
        <reference-list><record><articleInfo article-id="ART_CITED">
          <title-group><article-title lang="original">인용문헌</article-title></title-group>
          <citation-count kci="0"/></articleInfo></record></reference-list>
      </articleInfo></record></outputData></MetaData>"""))
    assert it["ids"]["kci_id"] == "ART_MAIN"
    assert it["title"]["ko"] == "본문"
    assert it["extra"]["citation_count_kci"] == "12"


def test_foreign_listed_does_not_scoop_publisher_names():
    """_all(rec, 'name') matched any <name> at any depth, so a publisher was
    reported as a foreign-index listing."""
    it = S._kci_record_to_item(_kci_rest_record("""
    <MetaData><outputData><record>
      <journalInfo><journal-name>한국사연구</journal-name>
        <publisher><name>한국사연구회</name></publisher>
        <foreign-listed><name>SCOPUS</name></foreign-listed></journalInfo>
      <articleInfo article-id="A"/></record></outputData></MetaData>"""))
    assert it["extra"]["foreign_listed"] == ["SCOPUS"]


def test_total_is_read_from_the_result_block():
    """A per-record <total> outranked the genuine one and drove breadth."""
    from defusedxml import ElementTree as DET

    root = DET.fromstring(b"""<MetaData><outputData>
      <record><articleInfo article-id="A"><total>37</total></articleInfo></record>
      <result><total>3</total></result></outputData></MetaData>""")
    assert S._kci_items(root)[1] == 3


def test_rest_success_is_structural_not_message_based(monkeypatch):
    """A success response carrying resultMsg='정상' was reported as
    KCI_REJECTED; a rejection with an empty resultMsg was reported as a
    legitimate empty result set."""
    import asyncio

    monkeypatch.setattr(S, "KCI_API_KEY", "dummy")

    async def serve(body):
        async def fake(url, params):
            return body, None
        monkeypatch.setattr(S, "_get", fake)
        return await S._kci_rest("articleSearch", {"title": "여성"})

    root, err = asyncio.run(serve("""<MetaData><outputData>
      <result><resultMsg>정상</resultMsg><total>1</total></result>
      <record><articleInfo article-id="A"/></record></outputData></MetaData>"""))
    assert err is None, "records present means success whatever resultMsg says"

    root, err = asyncio.run(serve("""<MetaData><outputData>
      <result><resultCode>ERR-401</resultCode><resultMsg/></result>
      </outputData></MetaData>"""))
    assert err is not None and err["code"] == "KCI_REJECTED"

    root, err = asyncio.run(serve("""<MetaData><outputData>
      <result><resultMsg>등록되지 않은 key 입니다.</resultMsg></result>
      </outputData></MetaData>"""))
    assert err is not None and err["code"] == "KCI_REJECTED"


def test_empty_doi_stubs_do_not_become_identifiers():
    """KCI emits a typed DOI element containing only the resolver prefix on
    records that have no DOI. Recovering the field naively replaced a null with
    a string that looks like an identifier."""
    assert S._clean_doi("http://dx.doi.org/") is None
    assert S._clean_doi("https://doi.org/") is None
    assert S._clean_doi("") is None
    assert S._clean_doi(None) is None
    assert S._clean_doi("http://dx.doi.org/10.15701/kcgs.2015.24.1.1") == \
        "10.15701/kcgs.2015.24.1.1"
    assert S._clean_doi("10.1234/abc.def") == "10.1234/abc.def"


def test_oai_tombstones_are_skipped():
    """Deleted records have no metadata; they parsed into all-null items and
    counted toward OAK's 99-record cap heuristic."""
    from defusedxml import ElementTree as DET

    root = DET.fromstring(b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
      <ListRecords><record><header status="deleted">
        <identifier>oai:oak.go.kr:1</identifier></header></record></ListRecords></OAI-PMH>""")
    recs = [r for r in root.iter() if S._ln(r) == "record"]
    assert len(recs) == 1 and S._is_deleted(recs[0])


def test_extended_hanja_is_not_classified_as_latin():
    """CJK Extension B and above were outside the Han ranges, so a rare-Hanja
    고서 title was routed to the English slot with a spurious romanisation
    warning — the Hangul bug, one block over."""
    assert M.detect_script("\U00020000\U0002A700") == "han"
    assert M.detect_script("\U0002F800") == "han"
    assert S._script_diags("\U00020000", "OAK") == []


def test_oak_abstract_keeps_both_languages():
    """abstract_h and abstract_e collapsed into one untagged field, dropping
    whichever came second."""
    items = [S._oak_item(r) for r in _oak_records()]
    assert items[2]["extra"]["abstract_en"] == "筆寫本."
    assert items[2]["extra"]["abstract_ko"] is None


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 to exercise the network")
def test_live_kci_oai_identifiers_are_typed():
    """The premise the OAI mapper was originally built on — 'a positional,
    untyped bag' — is false, and believing it discarded every DOI, every ISSN
    and the abstract. This pins the correction to the wire."""
    import asyncio
    import json

    out = json.loads(asyncio.run(S.kci_harvest("2019-05-01", "2019-05-01", max_records=100)))
    items = out["items"]
    assert len(items) == 100
    assert sum(1 for i in items if i["ids"]["issn"]) == 100, "ISSN is on every record"
    dois = [i["ids"]["doi"] for i in items if i["ids"]["doi"]]
    assert all(d.startswith("10.") for d in dois), (
        "a resolver prefix with no suffix is not a DOI and must not be emitted")
    assert all(i["ids"]["kci_id"] for i in items)
    assert sum(1 for i in items if i["extra"]["abstract_ko"] or i["extra"]["abstract_en"]) > 90


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 to exercise the network")
def test_live_max_records_is_a_cap():
    """The cap was checked after a batch was appended, so asking for 1 returned 100."""
    import asyncio
    import json

    out = json.loads(asyncio.run(S.kci_harvest("2026-07-01", "2026-07-01", max_records=5)))
    assert out["result"]["returned"] <= 5


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 to exercise the network")
def test_live_resumption_receipt_does_not_invent_a_window():
    """date_from/date_to are ignored when a resumption token is supplied. The
    receipt used to record them anyway — a provenance artefact naming a window
    that was never requested."""
    import asyncio
    import json

    first = json.loads(asyncio.run(S.kci_harvest("2019-05-01", "2019-05-02", max_records=100)))
    token = next((d["hint"] for d in first["diagnostics"]
                  if d["code"] == "OAI_MORE_AVAILABLE"), None)
    assert token, "expected more pages in this window"
    token = token.split("resumption_token='")[1].rstrip("'.")

    out = json.loads(asyncio.run(
        S.kci_harvest("1900-01-01", "1900-01-02", resumption_token=token, max_records=10)))
    assert "from" not in out["query"]["params"]
    assert out["query"]["params"]["resumptionToken"] == token
    assert not any("1900" in (d["message"] or "") for d in out["diagnostics"])


# ------------------------------------------------- deposit self-reporting ----


def _envelope():
    return M.build_envelope(
        server="korea_scholarship", operation="kci_search",
        input_terms="식민지", normalized="식민지", params={"title": "식민지"},
        matching_mode="metadata_conjunction", total=1, start=1, items=[],
        diagnostics=[M.diag("info", "OK", "1 record.", None)], attribution="KCI",
    )


def _codes(raw):
    return [d["code"] for d in json.loads(raw)["diagnostics"]]


def test_undeposited_response_says_so(monkeypatch):
    """The failure this guards is not a crash. Between 19 and 22 Aug 2026
    ndl-mcp called emit() at every exit with MCP_RECEIPT_LOG absent and
    deposited nothing, behind envelopes that looked entirely healthy. A
    response that is not being recorded has to say it is not being recorded."""
    monkeypatch.delenv("MCP_RECEIPT_LOG", raising=False)
    assert M.deposit_enabled() is False
    assert "RECEIPT_NOT_DEPOSITED" in _codes(M.emit(_envelope()))


def test_deposited_response_is_not_marked(monkeypatch, tmp_path):
    log = tmp_path / "receipts.jsonl"
    monkeypatch.setenv("MCP_RECEIPT_LOG", str(log))
    assert M.deposit_enabled() is True
    codes = _codes(M.emit(_envelope()))
    assert "RECEIPT_NOT_DEPOSITED" not in codes
    assert "RECEIPT_WRITE_FAILED" not in codes
    lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["script"] == "hangul"


def test_failed_write_is_distinguished_from_an_unset_variable(monkeypatch):
    """One is a choice and the other is a fault; they must not share a code."""
    monkeypatch.setenv("MCP_RECEIPT_LOG", "/proc/self/no/such/dir/receipts.jsonl")
    codes = _codes(M.emit(_envelope()))
    assert "RECEIPT_WRITE_FAILED" in codes
    assert "RECEIPT_NOT_DEPOSITED" not in codes
