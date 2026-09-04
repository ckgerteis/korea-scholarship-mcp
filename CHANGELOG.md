# Changelog

Versions are the thing to cite. A count produced under one release is not
reproducible against another, so the release actually used should be named in
the text and, where a version DOI exists, cited by it.

Releases earlier than those below are on the repository's releases page; this
file begins where the record is precise enough to be worth writing down.

## 0.5.0 — 2026-08-23

**Not released.** No tag was cut and no Zenodo record exists for this version, so
it is citable by commit alone. Tagging waits on confirmation that this
repository's Zenodo webhook is live: a release that mints nothing spends a
version number and returns nothing citable for it.

### Since 2026-09-04, still under 0.5.0 (unreleased)

- **Diagnostic level `warn` corrected to `warning` at eleven call sites.**
  `response-schema.json` closes `level` to `info`, `warning`, `error`, and
  `mediation.diag()` does not validate it, so every `SCRIPT_LATIN_QUERY`,
  `ZERO_CONJUNCTION`, `PAGE_PAST_END`, `TRUNCATED`, `BIBLIOMETRIC_SCOPE`,
  `OAI_*` and `WINDOW_DOMINATED_BY_ONE_REPOSITORY` diagnostic this server
  emitted failed schema validation. A consumer validating strictly would
  have rejected the envelope; one reading the level would have missed the
  warning. The codes and messages are unchanged.
- **`korea_sources_status` now reports the receipts destination the ledger
  actually uses.** It read `MCP_RECEIPT_LOG` only, so with `MCP_RECEIPT_DIR`
  set (the preferred form since 0.5.0) it reported `receipts_enabled: true`
  beside `receipt_log: null`, and its "not depositing" note named the wrong
  variable. It now asks `ledger.log_path_for()` and names both variables.
- `tests/smoke_stdio.py`: stdio handshake, `tools/list` checked against the
  README table, optional live call. Vendored byte-identical across the six.
- `response-schema.json`'s self-description said 2.2.0 and named four
  servers; it now says 2.3.0 and names six. Text only; the schema is unchanged.
- Module docstring banner corrected from v0.4.1 to v0.5.0.

- **A receipts folder, and one chain per server.** `ledger.py` 1.1.0 adds
  `MCP_RECEIPT_DIR`: point it at a directory and each server writes its own
  `<server>.jsonl` inside it. `MCP_RECEIPT_LOG` still names a single file and is
  honoured when `MCP_RECEIPT_DIR` is unset, so nothing existing breaks.
- **Why, precisely.** Appending is read-the-last-hash-then-write and `_LOCK` is a
  `threading.Lock`, which holds within one process and not between several. Six
  servers are six processes. Six of them writing 150 lines to one file produced
  **fourteen forks** — two lines claiming the same predecessor, over and over.
  That was measured, not inferred, and it means the family's shared log was never
  safe to verify as one chain. One writer per file removes the race rather than
  mitigating it.
- **`verify_chain()` now types its failures.** It reported everything as
  `prev_hash mismatch`. It distinguishes a **fork** (concurrent writers; every
  line still present, and the file is several chains rather than one), a
  **missing** line, a **reordering**, and **tamper** (a line that does not hash to
  its own content). Only the last is a claim about honesty, and a reader given one
  label for all four cannot tell a misconfiguration from interference.
- **`verify_dir()` and a manifest.** One pass over a receipts folder returns
  per-file verdicts, line counts, first and last timestamps and terminal hashes,
  plus combined totals by server, script and session. `<dist>-ledger manifest
  <dir>` writes it to `manifest.json`. That file is what a disclosure cites: one
  description of the deposit rather than six assertions to reconcile.
- `<dist>-ledger` gains `verify-dir` and `manifest`, and `verify` now exits
  non-zero when a chain does not verify.
- **`install.ps1` installs this server by default, not the family.** These are
  six independent packages — none imports another, none depends on another, and
  each installs alone. The installer defaulted to all six, so cloning one
  repository and running it would have registered five servers nobody asked for
  and fetched them from GitHub. It now resolves the default from the repository
  it sits in; `-All` opts into the family and `-Servers` names a subset.
- The verification step now **asserts that `ledger.py` and `mediation.py` are
  byte-identical across everything it installed** and stops if they are not.
  Nothing else enforces that invariant at install time, and two envelope
  versions in one environment is precisely the sort of thing that would be found
  later, in a deposit.
- **`install.ps1` installs the family.** Vendored byte-identical into all six
  repositories: it installs any or all of the six into one environment, asks once
  for the receipts folder and the session slug, and registers every server against
  the same pair. It prefers a sibling checkout to the network, carries across
  credentials already registered rather than asking again, and stops rather than
  guessing where the registered servers disagree about either value.
- **The server reports its build.** `initialize` was answered with an empty
  `serverInfo.version`. It now carries `__version__` where the SDK accepts one
  (mcp 2.x `MCPServer`). Under mcp 1.x, whose `FastMCP` takes no `version`, the
  field still reports the SDK's version rather than the server's — the argument
  is passed only where it is accepted.
- No layout change: this server was already packaged under `src/`, and the
  other five have now been brought to match it.
- The README installed a `0.4.0` wheel against a `0.4.1` `pyproject.toml`. The
  version is no longer written into the filename in that example.
- `CHANGELOG.md` and `response-schema.json` added to the sdist, so the source
  distribution carries the release record and the envelope contract that the
  README points at.

## 0.4.1 — 2026-08-22

**Never tagged.** This version was merged to `main` and no release was cut for
it; it has no tag and no DOI.

- **Every query-answering tool now deposits.** Nine of ten serialisation sites
  moved from `M.dumps` to `M.emit`. `mediation.py` 2.2.0 existed because the
  Korean copy had no `emit()`, so Korean queries never reached the ledger every
  Japanese query entered; the module was reconciled and the caller was not.
  Rejection paths are included: the disclosure standard asks for the log of
  queries *issued*, and a query issued and refused was still issued.
- `korea_sources_status` keeps `dumps` — it chooses no term and answers no
  corpus — but now reports the deposit state, distinguishing the two gates:
  whether `ledger.py` imported, and whether `MCP_RECEIPT_LOG` is set.
- `mediation.py` 2.3.0: the envelope reports whether it was deposited.
- Three tests added covering the unset, working, and unwritable deposit states.
