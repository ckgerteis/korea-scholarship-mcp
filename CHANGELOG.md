# Changelog

Versions are the thing to cite. A count produced under one release is not
reproducible against another, so the release actually used should be named in
the text and, where a version DOI exists, cited by it.

Releases earlier than those below are on the repository's releases page; this
file begins where the record is precise enough to be worth writing down.

## 0.6.2 — 2026-09-12

**The bundle's environment is built when it is installed, not during the first
connection.**

- **What was wrong.** 0.6.0 and 0.6.1 kept `pyproject.toml`, `uv.lock` and the
  entry point under `server/`. Claude Desktop's UV runtime looks for
  `pyproject.toml` at the bundle root when an extension is installed; finding
  it, it takes a uv already on the PATH or downloads its own (0.9.7 at the time
  of writing) and runs `uv sync` there behind a progress bar, so the interpreter and the libraries arrive before the server is ever
  launched. Not finding it, the app logs `missing pyproject.toml. Cannot
  proceed with UV setup`, installs the extension anyway, and the first
  connection attempt has to fetch uv, an interpreter and roughly 40 MB of
  libraries inside the launch timeout. That took 26 to 46 seconds on the
  author's connection against a limit of about sixty; on a Mac mini (M4,
  macOS 26.6.2) it never completed, and the app showed "Unable to connect to
  extension server" for the ndl, jstage and cinii bundles (reported
  7 September 2026); this bundle had the same layout and the same fault. Read from the app's code, not inferred: the install
  step, its root-path check and its log line, and the launch step that runs
  the app's own uv with the manifest's arguments from the bundle folder.
- **What changed.** `pyproject.toml`, `uv.lock` and `main.py` are at the
  bundle root and the manifest launches `uv run --directory ${__dirname}
  --frozen main.py`. The install-time `uv sync` now runs; measured on the
  ndl bundle with the app's uv 0.9.7 on an empty cache, install took 3 s and
  the launch answered `initialize` in 2.4 s, against 1.8 s for the same
  launch warm. Where a host skips the install step the launch still builds
  the environment itself.
- **The gate that would have caught it.** `tests/bundle_handshake.py` now
  runs the install phase before the launch, fails a bundle whose
  `pyproject.toml` is not at the root, and fails a launch that takes longer
  than thirty seconds to answer. The 0.6.1 bundle fails it. The previous gate
  allowed 240 seconds and launched without the install phase, which is why
  0.6.0 and 0.6.1 passed CI and did not run on the machine that reported them.
- Observed in the app, not only reproduced: the rebuilt ndl bundle installed
  on the author's machine under a test name, `main.log` shows `Setting up UV
  environment`, `Found system UV`, `Running uv sync` and `Setup completed
  successfully` six seconds later, then a launch that connected with all
  tools eight seconds after the launch line, and a live call answered. The
  same log's predecessor shows the 1.2.1 ndl layout installed on 8 September
  as `ndl-runtime-test` with the app recording `missing pyproject.toml. Cannot
  proceed with UV setup`; the line was there and went unread.

## 0.6.1 — 2026-09-08

- **The bundle no longer pins Python 3.13.** 0.6.0 shipped a `.python-version`
  so that every user ran the interpreter the release gate had run; the cost
  was a 20 MB interpreter download on first launch even where a usable Python
  was already installed. The file is gone: uv now takes any interpreter on
  the machine that satisfies `requires-python` (3.10 or later) and downloads
  one only where there is none. The lock resolves for every version in that
  range, and the handshake gate runs the bundle under 3.10 and 3.12 as well
  as on a cold cache before each release. Nothing in the server changed.

## 0.6.0 — 2026-09-08

**The Claude Desktop bundle runs again, on every supported interpreter.** The
same change as ndl-mcp 1.2.0, where it was proved before being copied here.

- **What was wrong.** Every `.mcpb` published so far imported under CPython
  3.12 and nothing else. `mcpb/build.py` vendored the dependencies with
  `pip install --target` under the interpreter running the build, the release
  workflow pinned that interpreter to 3.12, and `pydantic-core`, `rpds-py` and
  `cffi` ship native wheels tagged for one interpreter. The manifest meanwhile
  declared `runtimes.python >= 3.10` and launched bare `python` from the
  user's PATH, so Claude Desktop picked whatever satisfied the range, the
  import failed at module scope, and the user saw "Server disconnected".
- **What changed.** The manifest now declares `server.type: "uv"` (manifest
  0.4). Claude Desktop runs the bundle with uv, using a uv already on the
  PATH and otherwise the copy the app ships, from `server/pyproject.toml`,
  `server/.python-version` (3.13) and `server/uv.lock`. Nothing compiled is
  in the bundle, so one bundle serves Windows, macOS and Linux and is about
  100 KB instead of 10 to 17 MB. The first launch downloads Python 3.13 if the
  machine lacks it and the locked libraries, roughly 60 MB; measured on
  ndl-mcp at 26 s with a system 3.13 present and 46 s without, against Claude
  Desktop's 60 s request limit. A first launch that runs past the limit
  self-heals on restart, because uv caches what it fetched. Later launches
  take under a second.
- **`main.py` says what is wrong.** The import is guarded: on `ImportError`
  the entry point writes one line naming the running interpreter, its path
  and the supported range to stderr before re-raising. The `MCP_RECEIPT*`
  blank-stripping and every `user_config` field are unchanged.
- **A blank field in Claude Desktop's install dialog no longer becomes a
  folder or a credential.** Claude Desktop substitutes `${user_config.KEY}`
  only for fields that have a value and passes the placeholder verbatim
  otherwise, so a blank receipts folder became a folder named after the
  placeholder and a blank optional key would have been sent to the provider
  as the key. The entry point now drops any variable whose value still
  carries a placeholder before the package imports, and the handshake gate
  checks that it does.
- **A gate that would have caught this.** `tests/bundle_handshake.py`
  (vendored across the family) unpacks the built bundle, runs it exactly as
  the host would, and requires the `initialize` reply to name the manifest's
  version, on a cold cache and under interpreters other than the bundle's
  pin. The release workflow runs it on all three operating systems before
  anything is attached to a release.
- **CI matrix: 3.10, 3.12, 3.13 and 3.14.** 3.12 was the version the old
  bundles shipped and was never tested. The reported `import mcp` failure on
  3.14 (`TypeError: _eval_type() got an unexpected keyword argument
  'prefer_fwd_module'`) was re-tested: it is pydantic ≥ 2.12.4 meeting a 3.14
  interpreter built before the keyword landed (pydantic/pydantic#12544,
  #12597); 3.14.2, 3.14.3 and 3.14.7 are clean with pydantic 2.13.5.
  `requires-python` stays `>=3.10`; pre-release 3.14 builds are not
  supported.
- **The installers ask where to install, and never guess.** `install.py` and
  `install.ps1` chose the virtual environment silently and, run without a
  terminal, fell back to defaults for the receipts folder as well. Both now
  ask for the install location, the receipts folder and the session slug,
  offering a neutral suggestion that Enter accepts, and run without a
  terminal they stop before touching anything unless `--venv` and
  `--receipts-dir` (or `--no-receipts`; `-VenvDir`, `-ReceiptsDir`,
  `-NoReceipts` for PowerShell) say so. The author's own project slugs, which
  had served as examples in the installer help and the bundle's
  `user_config` description, are replaced with neutral ones.
- **A complete public repository.** `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant 2.1), `SECURITY.md`, issue forms that ask for the
  install route, the interpreter and the log tail, a pull request template,
  and Dependabot for the workflow actions and the Python dependencies.
  Repository topics and homepage set on GitHub.
- **The README says what the receipts are for.** A section after the opening
  explains, for a researcher rather than a maintainer, why a hash-chained
  record of every query matters: a citable search, negative findings that
  carry weight, a method section the manifest writes, a record of what an
  assistant actually asked, and nothing interpreted.
- **The README says where to get Python.** A "Getting Python" subsection at
  the head of Install: python.org on Windows with the PATH tick and the
  Microsoft Store stub explained, python.org or Homebrew on macOS, the
  distribution package on Linux, or uv on any of them.
- **Nothing here is specific to Claude, and the README now says so.** The
  server is a Model Context Protocol server over stdio; the bundle and the
  installers are conveniences for one client. A new "Any other MCP client"
  section gives the JSON any client takes and the `claude mcp add` line for
  Claude Code, with the receipts variables as optional environment.
- **The DOI is in the repository.** The Zenodo concept DOI is a badge under
  the README title and an identifier in `CITATION.cff`; neither carried it
  before, although every release has been archived.
- `tests/smoke_stdio.py` finds the console script through `sysconfig` and
  with its `.exe` suffix on Windows, so it no longer depends on the scripts
  directory being on PATH. Vendored across the family.
- `install.ps1` gains `-ConfigPath`, as `install.py` already had, and writes
  the configuration file as UTF-8 without a byte-order mark.
- README: how to read a "Server disconnected" log, where the log lives on
  each platform, and how an `ImportError` differs from a missing interpreter.
  Pins moved to v0.6.0.
- Workflow actions moved to their current majors; setup-uv is pinned exactly
  (v10.0.1) because it publishes no moving major tag past v7.

## 0.5.1 — 2026-09-08

- **Re-release, because v0.5.0 published without artefacts.** The v0.5.0
  workflow run built and uploaded the wheel, the sdist and three `.mcpb`
  bundles, but the release it attached them to was deleted and recreated by
  hand the same day (to fire the Zenodo webhook after the switch was turned
  on), and the recreated release carried no files. Every asset URL for
  v0.5.0 returns 404 while the README pointed users at it for a bundle. This
  release is the same code with a version bump; its purpose is a release that
  actually carries what the README promises. Nothing in the server changed.
- Note that the `.mcpb` bundles attached here still share the family's known
  runtime defect: they import only under CPython 3.12. That is fixed in the
  next release. Install with `pip` from the tag if your Python is 3.10–3.13.
- README: the suite pin was `bibliograph-mcp@v1.0.0`; the current suite
  release is v1.0.1.

## 0.5.0 — 2026-08-23

**Released 2026-09-04** as tag v0.5.0, archived by Zenodo as
[10.5281/zenodo.22305408](https://doi.org/10.5281/zenodo.22305408). The GitHub
release for this tag carries no wheel, sdist or bundle; see 0.5.1.

### Since 2026-09-04, still under 0.5.0 (unreleased)

- **Released on GitHub as a package.** `.github/workflows/release.yml` runs
  on a `vX.Y.Z` tag: tests on three OSes, wheel and sdist, one Claude
  Desktop `.mcpb` bundle per platform, then a GitHub release carrying all of
  them. Installable pinned to the tag with `pip install
  "git+https://github.com/ckgerteis/korea-scholarship-mcp@vX.Y.Z"` or `uvx --from`
  the same URL. The release is what fires the Zenodo webhook. Nothing is
  published to a package index.
- **Suite install.** `install.py` is the cross-platform port of `install.ps1`
  (Windows, macOS, Linux; same behaviour, importable). The family is also
  installable as one package, `bibliograph-mcp`, whose `bibliograph install`
  registers all six with one receipts folder.
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
