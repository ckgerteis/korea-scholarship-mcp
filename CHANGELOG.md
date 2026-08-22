# Changelog

Versions are the thing to cite. A count produced under one release is not
reproducible against another, so the release actually used should be named in
the text and, where a version DOI exists, cited by it.

Releases earlier than those below are on the repository's releases page; this
file begins where the record is precise enough to be worth writing down.

## 0.4.1 — 2026-08-22

First tagged release.

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
