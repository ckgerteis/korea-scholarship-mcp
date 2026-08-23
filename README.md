# korea-scholarship-mcp

A FastMCP stdio server exposing two Korean bibliographic services — the **Korea Citation Index** (KCI, 한국학술지인용색인, National Research Foundation of Korea) and **Open Access Korea** (OAK, 오픈액세스코리아, National Library of Korea) — as eight tools for Claude Desktop and other MCP clients.

It is the Korean counterpart to [`cinii-mcp`](https://github.com/ckgerteis/cinii-mcp) and [`jstage-mcp`](https://github.com/ckgerteis/jstage-mcp) and returns the same response envelope, so the three can be read side by side in trilateral work.

## What this is for

Korean-language scholarship, through the Korea Citation Index and Open Access Korea.

Search KCI for articles in Korean-registered journals; pull a full record with its abstract, author keywords, ISSN and UCI; follow the works a given article cites; read journal-level citation metrics. OAK reaches the institutional repositories — theses, monographs, research reports, 고서 holdings and open-access articles contributed by member institutions. Half the tools need no credentials at all, so Korean material is reachable the moment the server is installed.

Records come back in the same response envelope the Japanese servers use, which is what makes genuinely trilateral work practical: Japanese, Korean and Anglophone scholarship on one question, read side by side in one format.

## Tools

| Tool | Source | Key required | Purpose |
| --- | --- | --- | --- |
| `kci_search` | KCI REST | yes | Article search across title, author, journal, institution, affiliation, keyword, abstract, DOI, date range |
| `kci_article` | KCI REST | yes | Full record by control number — the only endpoint carrying keywords, ISSN, UCI and abstracts |
| `kci_references` | KCI REST | yes | Works cited by one article |
| `kci_journal_metrics` | KCI REST | yes | Journal citation indices (impact, immediacy, self-citation share) |
| `kci_harvest` | KCI OAI-PMH | **no** | Harvest by ingest-date window, filter client-side, follow resumption tokens |
| `oak_harvest` | OAK OAI-PMH | **no** | Harvest Korean institutional repositories by ingest-date window |
| `oak_record` | OAK OAI-PMH | **no** | One OAK record by OAI identifier |
| `korea_sources_status` | — | — | What is configured, what is reachable, and what this server does not cover |

Four of the eight work with no credentials at all — everything OAI-PMH, plus status.

## What the sources actually are

**KCI** indexes articles in Korean-registered scholarly journals. It does not index monographs, chapters, or dissertations. Its REST interface is a genuine query interface; its OAI-PMH interface is not.

**OAK** aggregates Korean institutional repositories — research reports, theses, monographs, 고서 holdings, OA articles — contributed unevenly by member institutions.

Both were probed live on 19 August 2026, and three properties shape how the tools are written:

1. **OAI datestamps are ingest dates, not publication dates.** A May 2019 harvest window returns articles published between 2010 and 2015. The often-repeated claim that KCI's OAI feed only exposes recent material is a misreading of this: the feed covers the corpus, it simply has no way to be *asked* anything. `kci_harvest` therefore filters client-side and says so in a diagnostic on every call.

1a. **KCI's oai_dc is fully typed, and this server reads the types.** Measured over 500 live records: `identifier[type=artiId|uci|doi|citedCnt|regularity|journalInfo]`, an `issn=` attribute on 500/500, and `lang="original|english"` on every title and description. Version 0.2.0 asserted the opposite — "a positional, untyped bag" to be matched by pattern — and consequently discarded every ISSN, every abstract, and 371 real DOIs per 500 records. Pattern matching survives only as a fallback for identifiers that arrive untagged. Note that KCI also emits `type="doi"` elements containing nothing but the resolver prefix; those are normalised to null rather than passed through as identifiers.

2. **OAK sends no `resumptionToken`.** It declares `noSetHierarchy`, honours `from`/`until`, and caps a window at roughly 99 records with no continuation. A harvester that trusts the protocol will silently present a truncated window as a complete one. `oak_harvest` raises `OAI_WINDOW_TRUNCATED` when it hits the cap and tells you to slice the window.

3. **OAK is not standard Dublin Core.** It emits `dc:title_h`, `dc:abstract_e`, `dc:publish_date`, `dc:location_org`, `dc:deep_link`, `dc:contents_url`, and puts the *material type* in `dc:keyword`. Field presence varies by contributing repository. Unrecognised fields are preserved under `extra.raw_fields` rather than dropped.

Two further asymmetries are reported rather than smoothed over:

- KCI's `articleSearch` accepts `keyword` as a **search** field but omits author keywords, ISSN and UCI from its **response**. An empty keywords list is an artefact of the endpoint. `kci_search` says so on every call; `kci_article` recovers them.
- KCI answers **HTTP 200 on failure**, putting the error in `outputData/result/resultMsg`. A client that checks status codes reports an unregistered key as a successful empty search.

## The response envelope

Every tool returns the envelope built by `mediation.py` and defined in [`response-schema.json`](response-schema.json), schema version 2.3.0 — typed `query`/`script`, `matching_mode`, graduated `breadth`, per-item `matched_in`, typed `diagnostics`, a loggable `receipt`, and `attribution`. Nothing is summarised or scored for you. `kci_search` also carries `searched_for`, the term actually sent with its detected script; the fetches and the harvests omit it, having chosen no term.

`mediation.py` 2.3.0 adds deposit reporting to 2.2.0, which was itself the reconciliation of a fork. Until 19 Aug 2026 two different files both called themselves 2.1.0: the Japanese copy had `emit()` — ledger persistence — but classified Hangul as `latin`; the Korean copy knew Hangul and the CJK extensions but had no `emit()`, so Korean queries never reached the deposit every Japanese query entered. 2.2.0 carries both, and is vendored byte-identical across cinii-mcp, jstage-mcp, ndl-mcp and this server. Everything in it is additive, so the Japanese servers adopt it without migration.

- `detect_script()` recognises Hangul and CJK Extensions B–G plus the Compatibility Supplement.
- `title` and `source` carry a `ko` slot alongside `ja`.
- `emit()` deposits the envelope to the hash-chained query ledger; `ledger_available()` reports whether it can, rather than leaving a silent no-op. As of v0.4.1 every query-answering tool in this server returns through `emit()`, rejections included — a query issued and refused was still issued — so Korean queries now enter the same deposit every Japanese query enters. `korea_sources_status` is the one exception: it chooses no term and answers no corpus, so it serialises with `dumps()` and instead *reports* the deposit state. Note the second gate: the ledger writes nothing unless `MCP_RECEIPT_LOG` is set, and `korea_sources_status` now says which of the two gates is closed when nothing is being written.

`title.romanized` stays `null` unless the source supplies a romanisation. Neither KCI nor OAK does, and this server will not generate one: Revised Romanisation of a Korean name requires knowing the name, and a machine-transliterated string presented as bibliographic data is a fabrication with the shape of a fact.

### Diagnostic codes

`OK` · `NO_KEY` · `KCI_REJECTED` · `KCI_KEYWORDS_ABSENT` · `ZERO_CONJUNCTION` · `TRUNCATED` · `PAGE_PAST_END` · `REFERENCE_DEPOSIT_UNEVEN` · `BIBLIOMETRIC_SCOPE` · `SCRIPT_LATIN_QUERY` · `INGEST_DATE_NOT_PUBLICATION_DATE` · `CLIENT_SIDE_FILTER` · `OAI_MORE_AVAILABLE` · `OAI_INCOMPLETE` · `OAI_STALLED` · `OAI_PAGE_CAP` · `OAI_NO_RECORDS` · `OAI_ERROR` · `OAI_WINDOW_TRUNCATED` · `OAK_NONSTANDARD_DC` · `WINDOW_DOMINATED_BY_ONE_REPOSITORY` · `REDIRECTED` · `TRANSPORT_ERROR` · `API_ERROR` · `PARSE_ERROR` · `RECEIPT_NOT_DEPOSITED` · `RECEIPT_WRITE_FAILED`

## Prerequisites

- Python 3.10+ on PATH.
- Optionally, a **KCI API key** — free, self-registered, required only for the four REST tools.

## Getting a KCI key

1. Register at [open.kci.go.kr](https://open.kci.go.kr/) and apply for an Open API key.
2. The same key serves all five `apiCode` values (`articleSearch`, `articleDetail`, `referenceSearch`, `citation`, `citationDetail`).

KCI is also mirrored as four datasets on [data.go.kr](https://www.data.go.kr/) under 한국연구재단; that route issues a different key and is not used here.

## Install

The package uses a `src/` layout and installs a console script. Any of these work:

```bash
# from a clone
pip install .

# from a built wheel, whatever its version
pip install dist/korea_scholarship_mcp-*.whl

# from a clone, for development
pip install -e ".[dev]"

# without installing anything, straight from the repository
uvx --from "git+https://github.com/ckgerteis/korea-scholarship-mcp" korea-scholarship-mcp
```

Installing puts a `korea-scholarship-mcp` command on PATH. `python -m korea_scholarship_mcp` is equivalent.

The package is namespaced, so it shares an environment with `cinii-mcp`,
`jstage-mcp`, `ndl-mcp`, `openalex-mcp` and `semantic-scholar-mcp` without
colliding. Verify the install with:

```bash
python -c "import korea_scholarship_mcp as k; print(k.__version__)"
```

Do not use `korea-scholarship-mcp --help` as the check: unknown arguments are
ignored, the server starts, reads end-of-input and exits 0, so it reports
success whatever the state of the code.

## Configuration

```bash
cp .env.example .env
```

```
KCI_API_KEY=your_kci_api_key_here
```

### Claude Desktop

If the package is installed, point at the console script:

```json
{
  "mcpServers": {
    "korea-scholarship": {
      "command": "C:\\path\\to\\.venv\\Scripts\\korea-scholarship-mcp.exe",
      "env": {
        "KCI_API_KEY": "your_kci_api_key_here"
      }
    }
  }
}
```

Or run it from a clone without installing:

```json
{
  "mcpServers": {
    "korea-scholarship": {
      "command": "C:\\path\\to\\.venv\\Scripts\\python.exe",
      "args": ["-m", "korea_scholarship_mcp"],
      "env": {
        "KCI_API_KEY": "your_kci_api_key_here"
      }
    }
  }
}
```

Omit the `env` block entirely to run the four keyless tools.

### A note on the MCP SDK

`mcp` 2.0.0 removed `mcp.server.fastmcp`. This server imports `FastMCP` where it exists and falls back to `MCPServer` where it does not, so it runs on either. The same shim was applied to `cinii-mcp` and `jstage-mcp` on 19 August 2026; before that, both imported `mcp.server.fastmcp` directly while pinning `mcp[cli]>=1.2.0` with no upper bound, so a fresh install of either resolved to 2.0.0 and failed at import.

## Credential handling

The KCI key travels in the query string, which makes it leak-prone in two specific ways this server closes:

- `httpx` logs every request URL at INFO. `_silence_http_logging()` mutes it and strips any stdout handler — necessary anyway, since stdout carries JSON-RPC.
- Transport and status exceptions embed the request URL. Every message bound for the client passes through `_redact()`, and the receipt is built from parameters with credentials removed rather than masked.

## Tests

```bash
python -m pytest tests -q                # offline, against fixtures captured 19 Aug 2026
RUN_LIVE=1 python -m pytest tests -q     # also exercises the live KCI endpoints
RUN_LIVE_OAK=1 python -m pytest tests -q # adds OAK; needs a network that reaches oak.go.kr
```

The live tests guard the claims this README rests on: that a KCI ingest window returns older publications, that KCI's identifiers are typed, that `max_records` is a cap rather than a hint, and that a resumption harvest does not record a date window it never sent. The OAK test is gated separately and **fails loudly** if OAK is unreachable rather than passing on an unexercised branch.

### Known limits

The four KCI REST tools have never seen a live response — there is no API key. Their field mapping follows the published documentation and is unverified against the wire; the success/failure test is deliberately structural (records present means success) so that neither a chatty success message nor a terse rejection is misread. Treat REST output as provisional until a key exists.

## What this server does not cover

**ScienceON (KISTI)** — deliberately out of scope. Its gateway requires an AES-256-CBC token built from a registered MAC address, plus a registered public IP. [`rubato103/scienceon-mcp`](https://github.com/rubato103/scienceon-mcp) already implements it against live credentials and is hardened against the exact credential-leak path described above; install it alongside rather than duplicating untestable auth code:

```bash
claude mcp add scienceon -- uvx --from "git+https://github.com/rubato103/scienceon-mcp" scienceon-mcp
```

**RISS (KERIS)** — the search API exists at `https://www.riss.kr/openApi` and covers theses, domestic and foreign articles, monographs, research reports and serials, but keys are issued only to Korean non-profit institutions and universities, each application approved by KERIS staff; individuals cannot apply. Whether a non-Korean university qualifies is untested. If a key is ever obtained, RISS belongs in this server.

**DBpia (Nurimedia)** — keys are open and generous (2,500 calls a day), but the terms of use restrict the service to non-commercial purposes *and* forbid copying, storing or transmitting search results, which are to be displayed in real time and unaltered. That is incompatible with harvesting into a reference manager, a corpus index, or a register. The constraint is the licence, not the API.

`korea_sources_status` reports all three of these in situ, so the omission is visible from inside the tool rather than only in this file.

## Usage rules

- KCI and OAK are public-sector services with no published rate limit. Harvest considerately; slice windows rather than hammering wide ranges.
- Metadata retrieved here is bibliographic. Full text sits behind whatever terms the holding repository sets — OAK's `contents_url` points into member repositories, each with its own licence.
- Attribution strings are returned in every envelope; carry them into anything published.

## Citation

If this software supports your research, please cite it. See [`CITATION.cff`](CITATION.cff), or use the "Cite this repository" button on GitHub.

## License

[MIT](LICENSE) © 2026 Christopher Gerteis.

This license covers the server code only. It grants no rights over KCI or OAK data, which remain governed by the terms of the National Research Foundation of Korea and the National Library of Korea respectively.

## Disclaimer

A research tool, maintained on a best-effort basis and provided "as is", without warranty. Not affiliated with or endorsed by the National Research Foundation of Korea, the National Library of Korea, KERIS, KISTI, or Nurimedia.

## Author

[Dr Christopher Gerteis](https://www.christophergerteis.net), SOAS University of London.
