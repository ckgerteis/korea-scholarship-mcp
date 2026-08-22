"""
Korea Scholarship MCP Server (v0.4.1)
=====================================
An MCP server for Korean-language scholarship: the Korea Citation Index (KCI,
한국학술지인용색인, National Research Foundation of Korea) and Open Access Korea
(OAK, 오픈액세스코리아, National Library of Korea).

It is the Korean counterpart to cinii-mcp and jstage-mcp and emits the same
response envelope (mediation.py, schema 2.2.0): typed query/script,
matching_mode, graduated breadth, per-item matched_in, typed diagnostics, a
loggable receipt, and attribution. No tool returns a server-composed summary.

Two access modes for KCI:
  * REST (KCI_API_KEY set) — real query interface, five apiCodes.
  * OAI-PMH (no key) — no query interface at all. Harvest by *ingest* date
    window, filter client-side. Verified 19 Aug 2026: a 2019 ingest window
    returns 2010–2015 publications, so the feed is not restricted to recent
    material; what it lacks is a way to ask a question.

OAK is OAI-PMH only, has no key, and is not standard oai_dc: it emits
dc:title_h, dc:abstract_e, dc:deep_link, dc:location_org and friends. Verified
19 Aug 2026: it declares noSetHierarchy, honours from/until, and returns no
resumptionToken — a window is silently capped at ~99 records. Every harvest
that hits the cap says so.

ScienceON (KISTI) is deliberately not implemented here. Its gateway needs an
AES-256-CBC token, a registered MAC address and a registered public IP, none
of which can be exercised without the operator's own approved credentials.
rubato103/scienceon-mcp already implements it against live credentials and has
been hardened against credential leakage through exception messages; install it
alongside rather than duplicating it. See the README.

No secret is embedded. KCI_API_KEY is read from the environment at runtime and
is redacted from every diagnostic, error and receipt this server emits.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Optional

import httpx
from defusedxml import ElementTree as DET

try:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ModuleNotFoundError:  # mcp SDK 2.x removed mcp.server.fastmcp
    from mcp.server.mcpserver import MCPServer as _MCPServer

from . import mediation as M

__version__ = "0.4.1"

# ==============================================================================
# Configuration
# ==============================================================================

KCI_API_KEY = os.environ.get("KCI_API_KEY", "")

KCI_REST_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
KCI_OAI_URL = "https://open.kci.go.kr/oai/request"
OAK_OAI_URL = "https://oak.go.kr/OAIHandler"

TIMEOUT = 45.0
USER_AGENT = f"korea-scholarship-mcp/{__version__} (+https://www.christophergerteis.net)"

KCI_ATTRIBUTION = (
    "Data via KCI (Korea Citation Index), National Research Foundation of Korea."
)
OAK_ATTRIBUTION = (
    "Data via OAK (Open Access Korea), National Library of Korea."
)

KCI_COVERAGE_NOTE = (
    "KCI indexes articles in Korean-registered scholarly journals. It does not "
    "index monographs, edited-volume chapters, or dissertations; for those, "
    "OAK institutional repositories and the RISS catalogue hold material KCI "
    "cannot see."
)
KCI_OAI_COVERAGE_NOTE = (
    "OAI-PMH has no query interface. Records are selected by KCI *ingest* "
    "datestamp, not publication date, and filtered client-side afterwards. A "
    "window is a slice of the accession stream, not of the literature."
)
OAK_COVERAGE_NOTE = (
    "OAK aggregates Korean institutional repositories: reports, theses, "
    "monographs, 고서 holdings and OA articles, contributed unevenly. Field "
    "presence varies by contributing repository — a missing date or abstract is "
    "usually the repository's silence, not the item's."
)

MODE_CONJ = "metadata_conjunction"
MODE_HARVEST = "harvest_window_filter"


def _silence_http_logging() -> None:
    """Two reasons, either sufficient on its own.

    httpx logs every request at INFO with the full URL — and the KCI key
    travels in the query string, so a default logging setup writes the
    credential into whatever stream the client is capturing.

    Second, this is a stdio server: stdout carries JSON-RPC and nothing else.
    Any handler that defaults to stdout corrupts the protocol frame.
    """
    for name in ("httpx", "httpcore", "httpx._client"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = False
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "stream", None) is sys.stdout:
            root.removeHandler(h)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))


_silence_http_logging()

mcp = _MCPServer("korea_scholarship_mcp")


# ==============================================================================
# Safety: nothing that has touched the key leaves this module
# ==============================================================================


def _redact(text: str) -> str:
    """Strip the API key from any string bound for the client.

    httpx embeds the full request URL in transport and status exceptions, and
    the KCI key travels in the query string. Without this, one network blip
    writes the key into the MCP response and from there into the transcript.
    """
    if not text:
        return text
    out = text
    if KCI_API_KEY:
        out = out.replace(KCI_API_KEY, "***REDACTED***")
    return re.sub(r"([?&]key=)[^&\s]+", r"\1***REDACTED***", out)


def _safe_params(params: dict) -> dict:
    """Parameters fit for the receipt: credentials removed, not masked."""
    return {k: v for k, v in params.items() if k not in ("key", "apiCode") and v not in (None, "")}


# ==============================================================================
# HTTP + XML
# ==============================================================================


async def _get(url: str, params: dict) -> tuple[Optional[str], Optional[dict]]:
    """GET returning (text, error_diag)."""
    try:
        # follow_redirects stays OFF: the KCI key travels in the query string and
        # httpx preserves the query across a redirect, so a 302 to any other host
        # would re-send the credential to it. A redirect is reported, not chased.
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
    except Exception as exc:  # noqa: BLE001
        return None, M.diag(
            "error",
            "TRANSPORT_ERROR",
            f"Network error ({type(exc).__name__}).",
            "Retry shortly. Korean government hosts occasionally refuse foreign traffic transiently.",
        )
    if resp.status_code in (301, 302, 303, 307, 308):
        return None, M.diag(
            "error",
            "REDIRECTED",
            f"HTTP {resp.status_code} redirect, not followed.",
            "The API key rides in the query string; following a cross-host redirect "
            "would disclose it. Check whether the endpoint has moved.",
        )
    if resp.status_code >= 400:
        return None, M.diag(
            "error",
            "API_ERROR",
            f"HTTP {resp.status_code} from {url.split('//')[-1].split('/')[0]}.",
            None,
        )
    return resp.text, None


def _parse(text: str) -> tuple[Optional[object], Optional[dict]]:
    try:
        return DET.fromstring(text.encode("utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, M.diag(
            "error", "PARSE_ERROR", f"Malformed XML ({type(exc).__name__}).", None
        )


def _ln(el) -> str:
    """Local name of an element, namespace discarded."""
    return el.tag.rsplit("}", 1)[-1]


def _first(el, name: str) -> Optional[str]:
    """First descendant with this local name, text stripped."""
    for child in el.iter():
        if _ln(child) == name and (child.text or "").strip():
            return child.text.strip()
    return None


def _all(el, name: str) -> list[str]:
    return [
        c.text.strip()
        for c in el.iter()
        if _ln(c) == name and (c.text or "").strip()
    ]


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _child(el, name):
    """First DIRECT-or-nested child block with this local name, searched from el.

    Returns the element, not its text, so callers can confine a lookup to one
    subtree. `_first`/`_all` walk every descendant, which is correct for a flat
    record and wrong the moment a record nests another record — a reference
    block inside an article, say. Then a single item is assembled from two
    different works with no diagnostic. Scope first, read second.
    """
    for c in el.iter():
        if _ln(c) == name:
            return c
    return None


def _first_in(el, name: str) -> Optional[str]:
    """_first confined to a subtree; None when el is None."""
    return _first(el, name) if el is not None else None


def _all_in(el, name: str) -> list[str]:
    return _all(el, name) if el is not None else []


def _pages(fpage: Optional[str], lpage: Optional[str]) -> Optional[str]:
    """Never render the string 'None' into a citation.

    Start-page-only and single-page records are ordinary, and an f-string over a
    missing lpage produced '17-None', which flows straight into a bibliography.
    """
    if fpage and lpage:
        return f"{fpage}-{lpage}"
    return fpage or lpage or None


# ==============================================================================
# KCI REST
# ==============================================================================


async def _kci_rest(api_code: str, params: dict) -> tuple[Optional[object], Optional[dict]]:
    """Call the KCI REST API.

    KCI returns HTTP 200 on failure and puts the error in the result block, so
    status codes decide nothing. The success test is deliberately *structural*
    rather than message-based: a response carrying <record> elements is treated
    as success whatever text sits in resultMsg, and a response with no records
    is treated as failure only when the service actually said something.

    The earlier version keyed solely on the presence of resultMsg, which is a
    coin flip in both directions — a success response carrying resultMsg="정상"
    became KCI_REJECTED, and a rejection with an empty resultMsg became a
    legitimate empty result set reported as ZERO_CONJUNCTION. Neither could be
    ruled out, because no live REST response has ever been observed.
    """
    if not KCI_API_KEY:
        return None, M.diag(
            "error",
            "NO_KEY",
            "KCI_API_KEY is not set; the REST interface is unavailable.",
            "Register at open.kci.go.kr for a key, or use kci_harvest, which needs none.",
        )
    q = {k: v for k, v in params.items() if v not in (None, "")}
    q["key"] = KCI_API_KEY
    q["apiCode"] = api_code
    text, err = await _get(KCI_REST_URL, q)
    if err:
        err["message"] = _redact(err["message"])
        return None, err
    root, err = _parse(text)
    if err:
        return None, err

    res = _child(root, "result")
    code = _first_in(res, "resultCode") if res is not None else None
    msg = _first_in(res, "resultMsg") if res is not None else _first(root, "resultMsg")
    has_records = any(_ln(el) == "record" for el in root.iter())

    if code and code.strip().upper() not in ("00", "0", "OK", "SUCCESS", "200"):
        return None, M.diag(
            "error", "KCI_REJECTED", _redact(f"{code}: {msg or '(no message)'}"),
            "resultCode reported a failure.",
        )
    if not has_records and msg:
        return None, M.diag(
            "error",
            "KCI_REJECTED",
            _redact(msg),
            "등록되지 않은 key 입니다 means the key is unknown; 사용기간이 종료되었습니다 "
            "means it has expired. If this message is in fact a success notice, the "
            "records were genuinely zero.",
        )
    return root, None


def _kci_authors(author_group) -> list[dict]:
    """KCI writes authors as `이름(소속기관)` with english= and orc-id= attributes."""
    out = []
    for a in author_group:
        if _ln(a) != "author":
            continue
        raw = _norm(a.text)
        name, affil = raw, None
        m = re.match(r"^(.*?)\s*[(（](.*)[)）]\s*$", raw)
        if m:
            name, affil = m.group(1).strip(), m.group(2).strip()
        out.append(
            {
                "name": name,
                "name_en": a.attrib.get("english") or None,
                "affiliation": affil,
                "orcid": a.attrib.get("orc-id") or None,
            }
        )
    return out


def _kci_record_to_item(rec) -> dict:
    """Map one KCI <record> to an envelope item.

    Every lookup is confined to the record's own journalInfo / articleInfo
    subtree. The earlier version searched all descendants, so on a record that
    nests another record it built one item out of two works — the cited work's
    control number beside the citing work's journal — and said nothing.

    NOTE: no live REST response has ever been observed (there is no key). This
    mapping follows the published field list and is unverified against the wire.
    """
    jinfo = _child(rec, "journalInfo")
    ainfo = _child(rec, "articleInfo")
    scope = ainfo if ainfo is not None else rec

    titles: dict[str, str] = {}
    tgroup = _child(scope, "title-group")
    for tel in (tgroup.iter() if tgroup is not None else []):
        if _ln(tel) == "article-title" and (tel.text or "").strip():
            titles.setdefault(tel.attrib.get("lang", "untagged"), _norm(tel.text))
    title_ko = titles.get("original")
    title_en = titles.get("english")
    untagged = titles.get("untagged")
    if untagged:
        if M.detect_script(untagged) == "latin":
            title_en = title_en or untagged
        else:
            title_ko = title_ko or untagged

    agroup = _child(scope, "author-group")
    authors = _kci_authors(agroup) if agroup is not None else []

    art_id = ainfo.attrib.get("article-id") if ainfo is not None else None
    citation_kci = citation_wos = None
    cc = _child(scope, "citation-count")
    if cc is not None:
        citation_kci = cc.attrib.get("kci")
        citation_wos = cc.attrib.get("wos")

    year_raw = _first_in(jinfo, "pub-year")
    try:
        year = int(year_raw) if year_raw else None
    except ValueError:
        year = None

    abstracts: dict[str, str] = {}
    abgroup = _child(scope, "abstract-group")
    for a in (abgroup.iter() if abgroup is not None else []):
        if _ln(a) == "abstract" and (a.text or "").strip():
            abstracts.setdefault(a.attrib.get("lang", "untagged"), _norm(a.text))

    kwgroup = _child(scope, "keyword-group")
    keywords = _all_in(kwgroup, "keyword")

    flisted = _child(jinfo, "foreign-listed") if jinfo is not None else None
    foreign = _all_in(flisted, "name")

    return M.make_item(
        title_ko=title_ko,
        title_en=title_en,
        authors=authors,
        journal_ko=_first_in(jinfo, "journal-name"),
        volume=_first_in(jinfo, "volume"),
        issue=_first_in(jinfo, "issue"),
        pages=_pages(_first_in(scope, "fpage"), _first_in(scope, "lpage")),
        year=year,
        doi=_clean_doi(_first_in(scope, "doi")),
        kci_id=art_id or _first_in(scope, "article-id"),
        uci=_first_in(scope, "uci"),
        issn=_first_in(jinfo, "issn"),
        url_ko=_first_in(scope, "url"),
        matched_in="metadata",
        record_type="article",
        extra={
            "publisher": _first_in(jinfo, "publisher-name"),
            "categories": _first_in(scope, "article-categories"),
            "keywords": keywords,
            "abstract_ko": abstracts.get("original"),
            "abstract_en": abstracts.get("english"),
            "citation_count_kci": citation_kci,
            "citation_count_wos": citation_wos,
            "fulltext_open": _first_in(scope, "orte-open-yn"),
            "foreign_listed": foreign,
        },
    )


def _kci_items(root) -> tuple[list[dict], int]:
    items = [
        _kci_record_to_item(rec) for rec in root.iter() if _ln(rec) == "record"
    ]
    # <total> is read from the result block, not from anywhere in the document:
    # a per-record <total> would otherwise outrank the real one and drive both
    # result.total and the breadth classification.
    res = _child(root, "result")
    total_raw = _first_in(res, "total") if res is not None else _first(root, "total")
    try:
        total = int(total_raw) if total_raw else len(items)
    except ValueError:
        total = len(items)
    return items, total


def _script_diags(query: str, corpus: str) -> list[dict]:
    """Raise the romanisation trap where it applies."""
    out = []
    script = M.detect_script(query)
    if query and script == "latin":
        out.append(
            M.diag(
                "warn",
                "SCRIPT_LATIN_QUERY",
                f"The query sent to {corpus} is in Latin script.",
                "Neither KCI nor OAK stores a romanisation. A Latin query reaches "
                "English-language title and abstract fields only, and will miss "
                "Korean-language scholarship entirely. Query in Hangul.",
            )
        )
    return out


# ==============================================================================
# KCI REST tools
# ==============================================================================


@mcp.tool()
async def kci_search(
    title: str,
    author: str = "",
    journal: str = "",
    institution: str = "",
    affiliation: str = "",
    keyword: str = "",
    abstract: str = "",
    doi: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    rows: int = 20,
) -> str:
    """Search KCI articles (REST, requires KCI_API_KEY).

    `title` is mandatory — the KCI API rejects a query without it, so a
    subject-led search must be run as a title query and again as a keyword
    query, and the two sets unioned by hand. `date_from`/`date_to` are YYYYMM.
    `rows` is capped at 100 by the API.

    Two asymmetries this tool reports rather than hides: articleSearch accepts
    `keyword` as a search field but omits author keywords, ISSN and UCI from
    its response, so an empty keywords list here means the endpoint did not
    return them, not that the article has none — use kci_article to recover
    them per record.
    """
    rows = max(1, min(int(rows), 100))
    page = max(1, int(page))
    params = {
        "title": title,
        "author": author,
        "journal": journal,
        "institution": institution,
        "affiliation": affiliation,
        "keyword": keyword,
        "abstract": abstract,
        "doi": doi,
        "dateFrom": date_from,
        "dateTo": date_to,
        "page": page,
        "displayCount": rows,
    }
    root, err = await _kci_rest("articleSearch", params)
    if err:
        return M.emit(
            M.build_envelope(
                server="korea_scholarship_mcp",
                operation="kci_search",
                input_terms=title,
                normalized=title,
                params=_safe_params(params),
                matching_mode=MODE_CONJ,
                total=0,
                start=0,
                items=[],
                diagnostics=[err],
                attribution=KCI_ATTRIBUTION,
                coverage_note=KCI_COVERAGE_NOTE,
            )
        )

    items, total = _kci_items(root)
    diags = _script_diags(title, "KCI")
    diags.append(
        M.diag(
            "info",
            "KCI_KEYWORDS_ABSENT",
            "articleSearch does not return author keywords, ISSN or UCI.",
            "An empty keywords list is an artefact of this endpoint. Call kci_article "
            "on a control number (ART…) to obtain them.",
        )
    )
    if total == 0:
        diags.append(
            M.diag(
                "warn",
                "ZERO_CONJUNCTION",
                "No record satisfies all supplied fields simultaneously.",
                "Drop the narrowest field and re-run; KCI conjoins every parameter.",
            )
        )
    requested_start = (page - 1) * rows
    if requested_start >= total > 0:
        diags.append(
            M.diag(
                "warn",
                "PAGE_PAST_END",
                f"page={page} starts at record {requested_start} of {total}.",
                "Reduce `page`. This is not a truncation — there is nothing there.",
            )
        )
    elif len(items) < min(rows, max(total - requested_start, 0)):
        diags.append(
            M.diag(
                "warn",
                "TRUNCATED",
                f"{len(items)} returned where {min(rows, total - requested_start)} were "
                f"expected; KCI sometimes ignores displayCount.",
                "Page through with `page` rather than trusting one call.",
            )
        )
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="kci_search",
            input_terms=title,
            normalized=title,
            params=_safe_params(params),
            matching_mode=MODE_CONJ,
            total=total,
            start=(page - 1) * rows,
            items=items,
            diagnostics=diags,
            attribution=KCI_ATTRIBUTION,
            coverage_note=KCI_COVERAGE_NOTE,
        )
    )


@mcp.tool()
async def kci_article(article_id: str) -> str:
    """Full KCI record for one control number (e.g. ART001995054).

    This is the only endpoint that carries author keywords, ISSN, author
    affiliations and the abstracts. Use it to repair records returned by
    kci_search.
    """
    params = {"id": article_id}
    root, err = await _kci_rest("articleDetail", params)
    if err:
        return M.emit(
            M.build_envelope(
                server="korea_scholarship_mcp",
                operation="kci_article",
                input_terms=article_id,
                normalized=article_id,
                params=params,
                matching_mode="identifier_lookup",
                total=0,
                start=0,
                items=[],
                diagnostics=[err],
                attribution=KCI_ATTRIBUTION,
                coverage_note=KCI_COVERAGE_NOTE,
            )
        )
    items, total = _kci_items(root)
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="kci_article",
            input_terms=article_id,
            normalized=article_id,
            params=params,
            matching_mode="identifier_lookup",
            total=total or len(items),
            start=0,
            items=items,
            diagnostics=[],
            attribution=KCI_ATTRIBUTION,
            coverage_note=KCI_COVERAGE_NOTE,
        )
    )


@mcp.tool()
async def kci_references(article_id: str) -> str:
    """Works cited by one KCI article (referenceSearch).

    KCI's reference data is contributed by publishers and is uneven: an empty
    list is as likely to mean the publisher deposited no reference block as
    that the article cites nothing. Read it as a floor, never a count.
    """
    params = {"id": article_id}
    root, err = await _kci_rest("referenceSearch", params)
    if err:
        diags, items, total = [err], [], 0
    else:
        items, total = _kci_items(root)
        diags = [
            M.diag(
                "info",
                "REFERENCE_DEPOSIT_UNEVEN",
                "KCI reference blocks are publisher-deposited and incomplete.",
                "Absence of references is not evidence that none were cited.",
            )
        ]
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="kci_references",
            input_terms=article_id,
            normalized=article_id,
            params=params,
            matching_mode="identifier_lookup",
            total=total,
            start=0,
            items=items,
            diagnostics=diags,
            attribution=KCI_ATTRIBUTION,
            coverage_note=KCI_COVERAGE_NOTE,
        )
    )


@mcp.tool()
async def kci_journal_metrics(
    journal: str = "",
    journal_id: str = "",
    year: str = "",
    years: int = 2,
) -> str:
    """KCI journal citation indices (impact factor, immediacy, self-citation share).

    Supply `journal` for the list view or `journal_id` for one journal's
    history. `years` must be 2–5.

    These are bibliometric artefacts of a national index with a small, largely
    domestic citing population. They measure position within KCI, not standing
    in a field, and should not be used to rank scholarship.
    """
    if not (2 <= int(years) <= 5):
        years = 2
    if journal_id:
        code, params = "citationDetail", {"id": journal_id}
    else:
        code, params = "citation", {"journal": journal, "year": year, "years": years}
    root, err = await _kci_rest(code, params)
    if err:
        items, total, diags = [], 0, [err]
    else:
        items, total = _kci_items(root)
        diags = [
            M.diag(
                "warn",
                "BIBLIOMETRIC_SCOPE",
                "KCI indices are computed inside the Korean citation population only.",
                "Not comparable with WoS or Scopus figures, and not a measure of quality.",
            )
        ]
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="kci_journal_metrics",
            input_terms=journal or journal_id,
            normalized=journal or journal_id,
            params=_safe_params(params),
            matching_mode=MODE_CONJ,
            total=total,
            start=0,
            items=items,
            diagnostics=diags,
            attribution=KCI_ATTRIBUTION,
            coverage_note=KCI_COVERAGE_NOTE,
        )
    )


# ==============================================================================
# OAI-PMH: KCI (keyless) and OAK
# ==============================================================================


def _oai_error(root) -> Optional[dict]:
    for el in root.iter():
        if _ln(el) == "error":
            code = el.attrib.get("code", "unknown")
            if code == "noRecordsMatch":
                return M.diag(
                    "info",
                    "OAI_NO_RECORDS",
                    "No records were ingested in this window.",
                    "Widen the from/until range. The window filters ingest dates, not publication dates.",
                )
            return M.diag("error", "OAI_ERROR", f"{code}: {_norm(el.text)}", None)
    return None


def _dc_map(rec) -> dict[str, list[str]]:
    """Collect every metadata child by local name, preserving order and repeats."""
    out: dict[str, list[str]] = {}
    for meta in rec.iter():
        if _ln(meta) != "metadata":
            continue
        for dc in meta:
            for el in dc:
                if (el.text or "").strip():
                    out.setdefault(_ln(el), []).append(_norm(el.text))
    return out


_KCI_ART_RE = re.compile(r"^ART\d+$")
_DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)")


def _clean_doi(raw: Optional[str]) -> Optional[str]:
    """Return a bare DOI, or None.

    KCI emits <identifier type="doi">http://dx.doi.org/</identifier> — the
    resolver prefix with nothing after it — on records that have no DOI at all.
    Verified 19 Aug 2026: in one ingest window every one of the eight typed DOI
    elements was this empty stub. Passing it through would put a string that
    looks like an identifier where a null belongs, which is worse than the
    omission it replaces.
    """
    if not raw:
        return None
    m = _DOI_RE.search(raw.strip())
    return m.group(1).rstrip(".,;)") if m else None
_KCI_CITE_RE = re.compile(r"^(?P<j>.+?),\s*(?P<v>[^,()]*?)\((?P<i>[^)]*)\)")


def _kci_oai_item(rec) -> dict:
    """Map one KCI OAI record.

    KCI's oai_dc is fully typed and this reads the types rather than guessing.
    Verified against 100 live records on 19 Aug 2026:

        identifier[type=artiId|uci|doi|citedCnt|regularity|journalInfo]
        identifier[issn=…]            on 100/100
        title[lang=original|english]  on 100/100
        description[lang=…]           on 100/100   (this is the abstract)

    An earlier version of this function asserted the identifiers were "a
    positional, untyped bag" to be matched by pattern. That was wrong — it came
    from a probe that read xml:lang, where KCI uses a bare lang, and so saw no
    attributes at all. The cost of the mistake was measurable: every DOI and
    every ISSN silently discarded, and the abstract never read.
    """
    ids: dict[str, str] = {}
    issn = None
    titles: dict[str, str] = {}
    descs: dict[str, str] = {}
    creators: list[str] = []
    subjects: list[str] = []
    publisher = date = url = language = rights = None
    untyped: list[str] = []
    # Untagged titles are a LIST, not one slot: a record with no lang attributes
    # carries the original and the English one after the other, and keying them
    # both to "untagged" silently kept whichever came first.
    untagged_titles: list[str] = []
    untagged_descs: list[str] = []

    for meta in rec.iter():
        if _ln(meta) != "metadata":
            continue
        for dc in meta:
            for el in dc:
                tag = _ln(el)
                val = _norm(el.text)
                if not val:
                    continue
                a = {k.rsplit("}", 1)[-1]: v for k, v in el.attrib.items()}
                if tag == "identifier":
                    kind = a.get("type")
                    if kind:
                        ids.setdefault(kind, val)
                    else:
                        untyped.append(val)
                    if a.get("issn"):
                        issn = issn or a["issn"]
                elif tag == "title":
                    lang = a.get("lang")
                    if lang:
                        titles.setdefault(lang, val)
                    else:
                        untagged_titles.append(val)
                elif tag == "description":
                    lang = a.get("lang")
                    if lang:
                        descs.setdefault(lang, val)
                    else:
                        untagged_descs.append(val)
                elif tag == "creator":
                    creators.append(val)
                elif tag == "subject":
                    subjects.append(val)
                elif tag == "publisher":
                    publisher = publisher or val
                elif tag == "date":
                    date = date or val
                elif tag == "url":
                    url = url or val
                elif tag == "language":
                    language = language or val
                elif tag == "rights":
                    rights = rights or val

    # Fall back to pattern matching only for identifiers that arrived untyped.
    kci_id = ids.get("artiId") or next((i for i in untyped if _KCI_ART_RE.match(i)), None)
    uci = ids.get("uci") or next((i for i in untyped if i.startswith("G704")), None)
    doi = _clean_doi(ids.get("doi")) or next(
        (d for d in (_clean_doi(i) for i in untyped) if d), None
    )
    citation = ids.get("journalInfo") or next(
        (i for i in untyped if "," in i and "(" in i), None
    )

    title_ko = titles.get("original")
    title_en = titles.get("english")
    for val in untagged_titles:
        if M.detect_script(val) == "latin":
            title_en = title_en or val
        else:
            title_ko = title_ko or val

    abstract_ko = descs.get("original")
    abstract_en = descs.get("english")
    for val in untagged_descs:
        if M.detect_script(val) == "latin":
            abstract_en = abstract_en or val
        else:
            abstract_ko = abstract_ko or val

    authors = []
    for blob in creators:
        for part in blob.split(";"):
            raw = _norm(part)
            if not raw:
                continue
            m = re.match(r"^(.*?)\s*[(（](.*)[)）]\s*$", raw)
            authors.append(
                {
                    "name": m.group(1).strip() if m else raw,
                    "name_en": None,
                    "affiliation": m.group(2).strip() if m else None,
                    "orcid": None,
                }
            )

    journal = volume = issue = pages = None
    if citation:
        m = _KCI_CITE_RE.match(citation)
        if m:
            journal, volume, issue = m.group("j"), m.group("v"), m.group("i")
        p = re.search(r"pp?\.\s*([\d\-–~]+)", citation)
        if p:
            pages = p.group(1)

    year = int(date[:4]) if date and re.match(r"^\d{4}", date) else None

    oai_id = None
    for h in rec.iter():
        if _ln(h) == "identifier" and (h.text or "").startswith("oai:"):
            oai_id = h.text.strip()
            break

    return M.make_item(
        title_ko=title_ko,
        title_en=title_en,
        authors=authors,
        journal_ko=journal,
        volume=volume,
        issue=issue,
        pages=pages,
        year=year,
        doi=doi,
        kci_id=kci_id,
        uci=uci,
        issn=issn,
        oai_id=oai_id,
        url_ko=url,
        matched_in="harvest",
        record_type="article",
        extra={
            "publisher": publisher,
            "subject": subjects,
            "language": language,
            "fulltext_open": rights or ids.get("regularity"),
            "citation_string": citation,
            "date_raw": date,
            "abstract_ko": abstract_ko,
            "abstract_en": abstract_en,
            "cited_count": ids.get("citedCnt"),
        },
    )


def _oak_item(rec) -> dict:
    """Map one OAK record.

    OAK is not standard oai_dc. It emits dc:title_h, dc:abstract_e,
    dc:publish_date, dc:location_org, dc:deep_link, dc:contents_url and
    dc:keyword (which holds the *material type*: Report, Book, OldBook, …).
    Anything unrecognised is preserved verbatim under extra.raw_fields rather
    than dropped, because the field set varies by contributing repository.
    """
    dc = _dc_map(rec)
    known = {
        "title_h", "title_e", "author", "publisher", "publish_date",
        "abstract_h", "abstract_e", "keyword", "location_org", "deep_link",
        "contents_url", "issn", "language",
    }
    title_h = (dc.get("title_h") or [None])[0]
    title_e = (dc.get("title_e") or [None])[0]
    title_ko = title_h if title_h and M.detect_script(title_h) != "latin" else None
    title_en = title_e or (title_h if title_h and M.detect_script(title_h) == "latin" else None)

    date = (dc.get("publish_date") or [None])[0]
    year = None
    if date:
        m = re.search(r"(1[5-9]\d{2}|20\d{2})", date)
        if m:
            year = int(m.group(1))

    oai_id = None
    for h in rec.iter():
        if _ln(h) == "identifier" and (h.text or "").startswith("oai:"):
            oai_id = h.text.strip()
            break

    kinds = dc.get("keyword", [])
    record_type = {
        "Report": "report", "Book": "book", "OldBook": "book",
        "Article": "article", "Thesis": "dissertation",
    }.get(kinds[0] if kinds else "", "unknown")

    return M.make_item(
        title_ko=title_ko,
        title_en=title_en,
        authors=[
            {"name": _norm(a), "name_en": None, "affiliation": None, "orcid": None}
            for a in dc.get("author", [])
        ],
        year=year,
        issn=(dc.get("issn") or [None])[0],
        oai_id=oai_id,
        url_ko=(dc.get("deep_link") or [None])[0],
        fulltext_url=(dc.get("contents_url") or [None])[0],
        holding_org=(dc.get("location_org") or [None])[0],
        matched_in="harvest",
        record_type=record_type,
        extra={
            "publisher": (dc.get("publisher") or [None])[0],
            "material_type": kinds,
            "abstract_ko": (dc.get("abstract_h") or [None])[0],
            "abstract_en": (dc.get("abstract_e") or [None])[0],
            "language": (dc.get("language") or [None])[0],
            "date_raw": date,
            "raw_fields": {k: v for k, v in dc.items() if k not in known},
        },
    )


def _is_deleted(rec) -> bool:
    """OAI tombstones carry status="deleted" and no metadata.

    Without this they parse into items with every field null, and then count
    toward the harvested total and toward OAK's 99-record cap heuristic — so a
    window of tombstones would be reported as a full window of records.
    """
    for h in rec.iter():
        if _ln(h) == "header" and h.attrib.get("status") == "deleted":
            return True
    return False


def _filter(items: list[dict], contains: str) -> list[dict]:
    """Client-side substring filter over titles, authors and holding org."""
    if not contains:
        return items
    needle = contains.lower()
    kept = []
    for it in items:
        hay = " ".join(
            [
                it["title"].get("ko") or "",
                it["title"].get("en") or "",
                " ".join(a["name"] for a in it["authors"]),
                it["source"].get("holding_org") or "",
                it["source"].get("journal_ko") or "",
            ]
        ).lower()
        if needle in hay:
            it["matched_in"] = "client_filter"
            kept.append(it)
    return kept


@mcp.tool()
async def kci_harvest(
    date_from: str,
    date_to: str,
    contains: str = "",
    set_spec: str = "ARTI",
    resumption_token: str = "",
    max_records: int = 200,
) -> str:
    """Harvest KCI by OAI-PMH — no API key required.

    `date_from`/`date_to` are YYYY-MM-DD and select on KCI *ingest* datestamp,
    not publication date: a July 2026 window returns articles published in
    2015. There is no query interface, so `contains` is applied client-side to
    whatever the window yielded. Sets: ARTI (article), ARTI_CONF (conference),
    JOUR (journal).

    This is a harvesting tool wearing a search tool's clothes. Treat a result
    as a slice of the accession stream, and say so in anything built on it.
    """
    max_records = max(1, min(int(max_records), 1000))
    params = (
        {"verb": "ListRecords", "resumptionToken": resumption_token}
        if resumption_token
        else {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "set": set_spec,
            "from": date_from,
            "until": date_to,
        }
    )
    items: list[dict] = []
    diags: list[dict] = []
    next_token = None
    pages = 0
    failed = False
    empty_pages = 0
    # Hard bound. The loop previously exited only on an empty token or on
    # reaching max_records, so a token that returns zero records satisfied
    # neither and the tool call hung while hammering the endpoint.
    MAX_PAGES = 200
    seen_tokens: set[str] = set()

    while True:
        text, err = await _get(KCI_OAI_URL, params)
        if err:
            diags.append(err)
            failed = True
            break
        root, err = _parse(text)
        if err:
            diags.append(err)
            failed = True
            break
        oerr = _oai_error(root)
        if oerr:
            diags.append(oerr)
            failed = oerr["level"] == "error"
            break
        batch = [_kci_oai_item(r) for r in root.iter()
                 if _ln(r) == "record" and not _is_deleted(r)]
        items.extend(batch)
        pages += 1
        empty_pages = empty_pages + 1 if not batch else 0
        next_token = None
        for el in root.iter():
            if _ln(el) == "resumptionToken" and (el.text or "").strip():
                next_token = el.text.strip()
        if not next_token or len(items) >= max_records:
            break
        if empty_pages >= 2:
            diags.append(M.diag(
                "warn", "OAI_STALLED",
                f"Two consecutive pages returned no records while still issuing a "
                f"resumption token; stopped after {pages} page(s).",
                "The cursor is not advancing. Narrow the window and retry."))
            next_token = None
            break
        if pages >= MAX_PAGES or next_token in seen_tokens:
            diags.append(M.diag(
                "warn", "OAI_PAGE_CAP",
                f"Stopped at the {MAX_PAGES}-page safety bound."
                if pages >= MAX_PAGES else "The resumption token repeated itself.",
                "Narrow the window rather than raising max_records."))
            break
        seen_tokens.add(next_token)
        params = {"verb": "ListRecords", "resumptionToken": next_token}

    # max_records is a cap, not a hint: the check above runs after a batch is
    # appended, so without this a request for 1 record returned 100.
    truncated_to_cap = len(items) > max_records
    if truncated_to_cap:
        items = items[:max_records]

    harvested = len(items)
    items = _filter(items, contains)
    diags.append(
        M.diag(
            "info",
            "INGEST_DATE_NOT_PUBLICATION_DATE",
            (f"{harvested} record(s) harvested by resumption token across {pages} page(s); "
             f"the date arguments were not sent and do not describe this set."
             if resumption_token else
             f"{harvested} record(s) harvested from ingest window {date_from}…{date_to} "
             f"across {pages} page(s)."),
            "Publication years inside this window are unrelated to the window itself.",
        )
    )
    if contains:
        diags.append(
            M.diag(
                "info",
                "CLIENT_SIDE_FILTER",
                f"'{contains}' matched {len(items)} of {harvested} harvested records.",
                "The filter saw only this window, not the KCI corpus. A zero here is not an absence in KCI.",
            )
        )
    if next_token and not failed:
        diags.append(
            M.diag(
                "warn",
                "OAI_MORE_AVAILABLE",
                f"Stopped at max_records={max_records}; the window has more.",
                f"Continue with resumption_token='{next_token}'.",
            )
        )
    elif next_token and failed:
        # Do not claim the cap was reached when the network gave out first.
        diags.append(
            M.diag(
                "warn",
                "OAI_INCOMPLETE",
                f"Harvest stopped early after {pages} page(s) because the request "
                f"failed, not because the cap was reached.",
                f"The set is partial. Resume with resumption_token='{next_token}'.",
            )
        )
    diags.extend(_script_diags(contains, "KCI"))
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="kci_harvest",
            input_terms=contains or f"{date_from}..{date_to}",
            normalized=contains,
            params=(
                {"resumptionToken": resumption_token, "contains": contains}
                if resumption_token
                else {"from": date_from, "until": date_to, "set": set_spec,
                      "contains": contains}
            ),
            matching_mode=MODE_HARVEST,
            total=harvested,
            start=0,
            items=items,
            diagnostics=diags,
            attribution=KCI_ATTRIBUTION,
            coverage_note=KCI_OAI_COVERAGE_NOTE,
        )
    )


@mcp.tool()
async def oak_harvest(
    date_from: str,
    date_to: str,
    contains: str = "",
) -> str:
    """Harvest Open Access Korea by OAI-PMH — no API key required.

    `date_from`/`date_to` are YYYY-MM-DD ingest datestamps. OAK declares no set
    hierarchy and — verified 19 Aug 2026 — sends no resumptionToken, so a
    window returns at most about 99 records and there is no way to ask for the
    rest. When the cap is hit this tool says so and tells you to narrow the
    window; it will not present a truncated window as a complete one.

    Windows are lumpy: a single repository's bulk deposit can fill one
    entirely, so the tool also reports which holding organisation dominates.
    """
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "from": date_from,
        "until": date_to,
    }
    diags: list[dict] = []
    items: list[dict] = []
    text, err = await _get(OAK_OAI_URL, params)
    if err:
        diags.append(err)
    else:
        root, perr = _parse(text)
        if perr:
            diags.append(perr)
        else:
            oerr = _oai_error(root)
            if oerr:
                diags.append(oerr)
            else:
                items = [_oak_item(r) for r in root.iter()
                         if _ln(r) == "record" and not _is_deleted(r)]

    harvested = len(items)
    if harvested >= 99:
        diags.append(
            M.diag(
                "warn",
                "OAI_WINDOW_TRUNCATED",
                f"{harvested} records returned and OAK sends no resumptionToken — the window is capped.",
                "Narrow date_from/date_to (a few days at a time) and harvest in slices. "
                "An uncapped window is the only kind you can treat as complete.",
            )
        )
    orgs: dict[str, int] = {}
    for it in items:
        org = it["source"].get("holding_org")
        if org:
            orgs[org] = orgs.get(org, 0) + 1
    if orgs:
        top, n = max(orgs.items(), key=lambda kv: kv[1])
        if harvested and n / harvested >= 0.5:
            diags.append(
                M.diag(
                    "warn",
                    "WINDOW_DOMINATED_BY_ONE_REPOSITORY",
                    f"{n} of {harvested} records in this window come from {top}.",
                    "This window records one repository's deposit event, not a cross-section of Korean OA output.",
                )
            )

    items = _filter(items, contains)
    if contains:
        diags.append(
            M.diag(
                "info",
                "CLIENT_SIDE_FILTER",
                f"'{contains}' matched {len(items)} of {harvested} harvested records.",
                "OAK has no query interface; the filter saw only this window.",
            )
        )
    diags.append(
        M.diag(
            "info",
            "OAK_NONSTANDARD_DC",
            "OAK emits dc:title_h / dc:abstract_e / dc:deep_link rather than standard Dublin Core.",
            "Unrecognised fields are preserved under extra.raw_fields; field presence varies by repository.",
        )
    )
    diags.extend(_script_diags(contains, "OAK"))
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="oak_harvest",
            input_terms=contains or f"{date_from}..{date_to}",
            normalized=contains,
            params={"from": date_from, "until": date_to, "contains": contains},
            matching_mode=MODE_HARVEST,
            total=harvested,
            start=0,
            items=items,
            diagnostics=diags,
            attribution=OAK_ATTRIBUTION,
            coverage_note=OAK_COVERAGE_NOTE,
        )
    )


@mcp.tool()
async def oak_record(identifier: str) -> str:
    """One OAK record by OAI identifier (oai:oak.go.kr:NNNNNNNN, or the bare number)."""
    ident = identifier if identifier.startswith("oai:") else f"oai:oak.go.kr:{identifier}"
    params = {"verb": "GetRecord", "identifier": ident, "metadataPrefix": "oai_dc"}
    items: list[dict] = []
    diags: list[dict] = []
    text, err = await _get(OAK_OAI_URL, params)
    if err:
        diags.append(err)
    else:
        root, perr = _parse(text)
        if perr:
            diags.append(perr)
        else:
            oerr = _oai_error(root)
            if oerr:
                diags.append(oerr)
            else:
                items = [_oak_item(r) for r in root.iter()
                         if _ln(r) == "record" and not _is_deleted(r)]
    return M.emit(
        M.build_envelope(
            server="korea_scholarship_mcp",
            operation="oak_record",
            input_terms=identifier,
            normalized=ident,
            params={"identifier": ident},
            matching_mode="identifier_lookup",
            total=len(items),
            start=0,
            items=items,
            diagnostics=diags,
            attribution=OAK_ATTRIBUTION,
            coverage_note=OAK_COVERAGE_NOTE,
        )
    )


# ==============================================================================
# Status
# ==============================================================================


@mcp.tool()
async def korea_sources_status() -> str:
    """Report which Korean sources are configured and reachable right now.

    Checks the KCI REST key, the two keyless OAI endpoints, and states plainly
    what this server does not cover (ScienceON, RISS, DBpia) and why.
    """
    checks: list[dict] = []

    kci_rest = {"source": "KCI REST", "key_present": bool(KCI_API_KEY)}
    if KCI_API_KEY:
        root, err = await _kci_rest("articleSearch", {"title": "테스트", "displayCount": 1})
        kci_rest["reachable"] = err is None or err["code"] != "TRANSPORT_ERROR"
        kci_rest["accepted"] = err is None
        kci_rest["note"] = None if err is None else _redact(err["message"])
    else:
        kci_rest["reachable"] = None
        kci_rest["accepted"] = False
        kci_rest["note"] = "KCI_API_KEY unset — kci_search / kci_article / kci_references / kci_journal_metrics are unavailable."
    checks.append(kci_rest)

    for name, url in (("KCI OAI-PMH", KCI_OAI_URL), ("OAK OAI-PMH", OAK_OAI_URL)):
        text, err = await _get(url, {"verb": "Identify"})
        entry = {"source": name, "key_present": None, "accepted": err is None}
        entry["reachable"] = err is None
        if err is None and text:
            root, perr = _parse(text)
            entry["repository"] = _first(root, "repositoryName") if not perr else None
            entry["earliest_datestamp"] = _first(root, "earliestDatestamp") if not perr else None
        entry["note"] = None if err is None else err["message"]
        checks.append(entry)

    not_covered = [
        {
            "source": "ScienceON (KISTI)",
            "reason": "Requires an AES-256-CBC token, a registered MAC address and a registered "
                      "public IP. Implemented and live-verified by rubato103/scienceon-mcp; "
                      "install that alongside rather than duplicating untested auth code here.",
        },
        {
            "source": "RISS (KERIS)",
            "reason": "Search API keys are issued to Korean non-profit institutions and universities "
                      "only, each application approved by KERIS staff; individuals cannot apply.",
        },
        {
            "source": "DBpia (Nurimedia)",
            "reason": "Keys are open, but the terms of use forbid copying, storing or transmitting "
                      "search results — incompatible with harvesting into a reference manager or corpus.",
        },
    ]

    # Whether the deposit is actually happening, reported rather than assumed.
    # There are two independent gates and only one of them is about this code:
    # ledger_available() answers whether ledger.py imported at all, and
    # ledger.enabled() answers whether MCP_RECEIPT_LOG is set. If either is
    # false, mediation.emit() degrades to dumps() and every query goes
    # unrecorded with no error to notice. A server that reports what is
    # configured must report this, or the silence is its own.
    ledger_module = M.ledger_available()
    receipts_on = False
    receipt_log = receipt_session = None
    try:
        from . import ledger as _ledger
        receipts_on = bool(_ledger.enabled())
        receipt_log = os.environ.get("MCP_RECEIPT_LOG") or None
        receipt_session = os.environ.get("MCP_RECEIPT_SESSION") or None
    except Exception:  # pragma: no cover - ledger.py absent is a valid config
        ledger_module = False

    if ledger_module and receipts_on:
        deposit_note = (
            "Depositing. Every query envelope is written to the append-only, "
            "hash-chained log before the response is returned."
        )
    elif not ledger_module:
        deposit_note = (
            "NOT depositing: ledger.py did not import, so mediation.emit() "
            "degrades to dumps(). Searches run normally and no receipt survives them."
        )
    else:
        deposit_note = (
            "NOT depositing: MCP_RECEIPT_LOG is unset, so every deposit call "
            "returns without writing. Searches run normally and no receipt "
            "survives them. Set MCP_RECEIPT_LOG before any session whose "
            "queries are meant to be citable evidence — a receipt cannot be "
            "reconstructed afterwards."
        )

    deposit = {
        "ledger_module_importable": ledger_module,
        "receipts_enabled": receipts_on,
        "receipt_log": receipt_log,
        "receipt_session": receipt_session,
        "note": deposit_note,
    }

    return M.dumps(
        {
            "server": "korea_scholarship_mcp",
            "schema_version": M.SCHEMA_VERSION,
            "version": __version__,
            "operation": "korea_sources_status",
            "checks": checks,
            "deposit": deposit,
            "not_covered": not_covered,
            "attribution": f"{KCI_ATTRIBUTION} {OAK_ATTRIBUTION}",
        }
    )


def main() -> None:
    """Console-script entry point (`korea-scholarship-mcp`)."""
    mcp.run()


if __name__ == "__main__":
    main()
