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
