# korea-scholarship-mcp

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22305407.svg)](https://doi.org/10.5281/zenodo.22305407)

A FastMCP stdio server exposing two Korean bibliographic services — the **Korea Citation Index** (KCI, 한국학술지인용색인, National Research Foundation of Korea) and **Open Access Korea** (OAK, 오픈액세스코리아, National Library of Korea) — as eight tools for Claude Desktop and other MCP clients.

It is the Korean counterpart to [`cinii-mcp`](https://github.com/ckgerteis/cinii-mcp) and [`jstage-mcp`](https://github.com/ckgerteis/jstage-mcp) and returns the same response envelope, so the three can be read side by side in trilateral work.

## What this is for

Korean-language scholarship, through the Korea Citation Index and Open Access Korea.

Search KCI for articles in Korean-registered journals; pull a full record with its abstract, author keywords, ISSN and UCI; follow the works a given article cites; read journal-level citation metrics. OAK reaches the institutional repositories — theses, monographs, research reports, 고서 holdings and open-access articles contributed by member institutions. Half the tools need no credentials at all, so Korean material is reachable the moment the server is installed.

Records come back in the same response envelope the Japanese servers use, which is what makes genuinely trilateral work practical: Japanese, Korean and Anglophone scholarship on one question, read side by side in one format.

## What the receipts are for

A search you cannot re-run is a claim you cannot check. When a footnote rests on a database
query, say that no article in this index uses a term before a certain year, the reader is asked to
take the search on trust: which term, in which script, on what date, against which index and which
version of it, and how far down the results the author went. Ordinary searching leaves none of
that behind. This server leaves all of it. Every
query-answering tool returns its envelope through the ledger, which appends one line to an
append-only file: the term actually sent and its script, how the source matched it, how many
records existed and how many came back, the diagnostics, the tool and its parameters, the server
version, a timestamp, and the hash of the previous line. The hash makes the file a chain: a line
cannot be altered, removed or reordered afterwards without the verifier saying so.

What that gives a researcher:

- **A citable search.** Name the receipt in the footnote (session slug, server, date, line hash)
  and a reader can see exactly what was asked and run it again against the same version.
- **Negative findings that carry weight.** "Not found" is evidence only if the search that
  produced it is on record, with its term, its script and its breadth.
- **A method section that writes itself.** `korea-scholarship-mcp-ledger` `manifest <folder>` summarises every
  query a project made, by server, script and session: the disclosure a journal, a
  data-availability statement or a research-integrity review asks for.
- **A record of AI-mediated research.** When a model chose the term, the receipt shows the term
  it chose and what came back, which is the thing to disclose about work done with an assistant.
- **Nothing interpreted.** The receipt is the source's own answer with credentials removed. The
  server does not summarise, rank or paraphrase, so the record is of the source, not of the tool.

Receipts are off until you name a folder (`MCP_RECEIPT_DIR`); each server then writes its own
`<server>.jsonl` inside it, and `MCP_RECEIPT_SESSION` stamps a project or article slug on every
line so one folder can serve several projects. `korea-scholarship-mcp-ledger` `verify-dir <folder>` checks the chains.
The mechanics, the variables and what the envelope says when nothing is deposited are in the
receipts section below.

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
- `emit()` deposits the envelope to the hash-chained query ledger; `ledger_available()` reports whether it can, rather than leaving a silent no-op. As of v0.4.1 every query-answering tool in this server returns through `emit()`, rejections included — a query issued and refused was still issued — so Korean queries now enter the same deposit every Japanese query enters. `korea_sources_status` is the one exception: it chooses no term and answers no corpus, so it serialises with `dumps()` and instead *reports* the deposit state. Note the second gate: the ledger writes nothing unless `MCP_RECEIPT_DIR` (a receipts folder, one hash-chained file per server) or the legacy `MCP_RECEIPT_LOG` is set, and `korea_sources_status` now says which of the two gates is closed when nothing is being written.

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

Three routes. All three give you the same server; pick by how much you want to see of it.

**Python.** The pip and source routes need Python 3.10 or later; 3.10, 3.12, 3.13 and 3.14 are tested in CI on Windows, macOS and Linux. The Claude Desktop bundle uses whichever of these is already installed, and has uv download one only if none is.

### Getting Python

Every route needs Python 3.10 to 3.14. The Claude Desktop bundle uses one already on the machine
and has uv download one only if none is; the other routes also need the `venv` module, which the
official installers include.

- **Windows.** Download the 64-bit installer from [python.org/downloads](https://www.python.org/downloads/)
  and run it; tick "Add python.exe to PATH" on the first screen. Afterwards `py --version` (the
  launcher the installer adds) or `python --version` in a new terminal should print 3.1x. If typing
  `python` opens the Microsoft Store instead, Windows has no Python yet: that Store page is a stub,
  and it is also what "'python' is not recognized" usually means.
- **macOS.** The [python.org installer](https://www.python.org/downloads/macos/), or
  `brew install python@3.13` with [Homebrew](https://brew.sh). The `/usr/bin/python3` that Xcode's
  command-line tools provide may be older than 3.10; `python3 --version` says.
- **Linux.** Your distribution's package: `sudo apt install python3 python3-venv` on Debian and
  Ubuntu, `sudo dnf install python3` on Fedora. Or let uv provide one (next line).
- **Any platform, with uv.** [uv](https://docs.astral.sh/uv/getting-started/installation/)
  installs Python itself: `uv python install 3.13`, then `uv venv` or the `uvx` route below.

### One click: the Claude Desktop bundle

Download `korea-scholarship-mcp-0.6.1.mcpb` from the [latest release](https://github.com/ckgerteis/korea-scholarship-mcp/releases/latest) and open it; Claude Desktop installs it. One bundle serves Windows, macOS (Apple Silicon and Intel) and Linux. Claude Desktop asks for KCI API key and a receipts folder at install time; the key is stored in the OS keychain.

The bundle carries the server's source and a lock file, nothing compiled, and needs no Python of its own: Claude Desktop runs it with [uv](https://docs.astral.sh/uv/), using a uv already on your PATH if there is one and otherwise the copy the app ships. On first launch uv uses a Python 3.10 or later already on the machine, downloading one only if there is none, and installs the locked libraries: roughly 40 MB, or 60 MB with an interpreter, which took 26 to 46 seconds on the author's connection; later launches take under a second. If the first launch is slow enough that Claude Desktop reports the server disconnected, restart the app: what uv already fetched is cached, and the second launch completes. Bundles before 0.6.0 vendored libraries compiled for CPython 3.12 only and failed on every other interpreter; see [Troubleshooting](#troubleshooting).

### From GitHub, pinned to a release

```bash
pip install "git+https://github.com/ckgerteis/korea-scholarship-mcp@v0.6.1"
# or, without an environment of your own:
uvx --from "git+https://github.com/ckgerteis/korea-scholarship-mcp@v0.6.1" korea-scholarship-mcp
```

installs the `korea-scholarship-mcp` console script and `korea-scholarship-mcp-ledger`. The tag is the thing to cite; `@main` gets whatever is current. Then register it in Claude Desktop (below), or let `install.py` do that.

### The whole family

```bash
pip install "git+https://github.com/ckgerteis/bibliograph-mcp@v1.0.3" && bibliograph install
```

installs all six servers and registers them together — one receipts folder, credentials asked for once. See [bibliograph-mcp](https://github.com/ckgerteis/bibliograph-mcp). From a checkout of this repository, `python install.py` does the same for this server alone, `python install.py --all` for the six, on Windows, macOS and Linux; `install.ps1` remains for Windows.

### From source

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

### Installing more than this one

Six independent packages. None imports another, none depends on another, and
each installs and answers on its own — `pip install .` in this directory is a
complete install of this server and nothing else.

They do share three things: a response envelope, a query ledger, and — if you
run more than one — a receipts folder. `install.ps1` is vendored byte-identical
into all six and handles that on Windows; `install.py` is its cross-platform port. **Both install this server by default**, because
cloning one repository is not a request for five more.

```powershell
.\install.ps1                        # this server
.\install.ps1 -All                   # all six
.\install.ps1 -Servers korea_scholarship,cinii# a chosen subset
```

Nothing about where things go is decided for you. The script asks where to
install (the virtual environment Claude Desktop will be pointed at), which
folder receives the receipts, and which session slug to stamp on them,
offering a neutral suggestion for each that Enter accepts; run without a
terminal it does not guess, and stops unless `--venv` and `--receipts-dir`
(or `--no-receipts`; `-VenvDir` and `-ReceiptsDir` for `install.ps1`) say
so. Whatever subset you name is registered against one receipts folder, asked for
once. The script prefers a sibling checkout to the network, carries across
credentials already registered rather than asking again, leaves servers it was
not asked about alone, and stops rather than guessing where the servers already
registered disagree about the folder or the session slug. It also asserts that
`ledger.py` and `mediation.py` are byte-identical across everything it
installed, so two envelope versions cannot end up in one environment unnoticed.

### Any other MCP client

Nothing here is specific to Claude. The server speaks the Model Context Protocol over stdio and
nothing else: any client that can start a process and talk JSON-RPC to it (Claude Code, Cursor,
VS Code and Continue, Zed, LibreChat, a script of your own using an MCP SDK) can use it. The
Claude Desktop bundle and the installers are conveniences for one client; the server underneath is
the same console script. Register it anywhere by giving the client the absolute path of the
console script and, optionally, the environment:

```json
{
  "mcpServers": {
    "korea_scholarship": {
      "command": "/absolute/path/to/.venv/bin/korea-scholarship-mcp",
      "env": {
        "KCI_API_KEY": "your key (optional; four tools need none)",
        "MCP_RECEIPT_DIR": "/absolute/path/to/receipts",
        "MCP_RECEIPT_SESSION": "project-or-article-slug"
      }
    }
  }
}
```

Claude Code takes the same thing on the command line:

```bash
claude mcp add korea_scholarship -- /absolute/path/to/.venv/bin/korea-scholarship-mcp
```

On Windows the path ends in `\.venv\Scripts\korea-scholarship-mcp.exe`. `MCP_RECEIPT_DIR` and `MCP_RECEIPT_SESSION`
are optional; without them the server runs and every envelope says `RECEIPT_NOT_DEPOSITED`. The
stdio transport is the only one: there is no HTTP endpoint to expose, and nothing to host.

## Troubleshooting

**"Server disconnected"** is all Claude Desktop says when the server process exited before or during the handshake, whatever the reason. The reason is in the log:

- Windows: `%APPDATA%\Claude\logs\mcp-server-<name>.log` (the extension's display name, or the key under `mcpServers`), with `mcp.log` beside it for the app's side of the conversation.
- macOS: `~/Library/Logs/Claude/mcp-server-<name>.log` and `mcp.log`.
- Linux: `~/.config/Claude/logs/`.

Read the last launch from the bottom up. Three shapes account for nearly every report:

- **A Python traceback ending in `ImportError` or `ModuleNotFoundError`** (for example `No module named 'pydantic_core._pydantic_core'`). The interpreter started, the code was found, and a compiled library did not match that interpreter. This is what every bundle before 0.6.0 did on any Python other than 3.12. Install the current bundle, or use the pip route, which resolves wheels for the interpreter you install into.
- **`'python' is not recognized`, `spawn python ENOENT`, or a line from the Microsoft Store**: no interpreter was found on the PATH Claude Desktop constructs. Nothing of this server ran. The current bundle does not launch `python` at all; for the pip route, register the console script by absolute path as shown above.
- **A line from uv** (`error: ...`, or a download that never finished): the current bundle's runtime could not build its environment, usually because the first launch had no network or ran past Claude Desktop's sixty-second limit. Restart the app; uv keeps what it fetched. A uv older than 0.5 cannot read the lock file; upgrade it or remove it so the app uses its own.

The bundle's own entry point writes one line naming the interpreter, its path and the supported range before re-raising an import failure, so a log from 0.6.0 onwards says which of these it is.

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

`tests/smoke_stdio.py` starts the installed console script over stdio, performs the MCP handshake, and checks `tools/list` against the tool table above; `RUN_LIVE=1 … <tool> '<json params>'` adds one live call.

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
