# PROTO-2.2 acceptance receipt

Started **2026-10-25** from `main` at `b0ac9f9` (PROTO-2.1).
Status: **working prototype acceptance complete**; [canonical acceptance ledger](PROTOTYPE_PLAN.md).
Exact publication hash, live remote agreement and fresh CI are checked after this receipt's commit
and reported in the closing response; the baseline run below does not establish those results.

## Scope and preservation

Rehearse documented startup and disposable Core recovery; confirm AC-01–10,
run required final gates, reconcile current entry documents, publish only reviewed safe changes,
then verify local/tracking/live remote agreement and CI separately. No next phase starts here.
Existing native/provider changes remain held. Runtime data and synthetic credentials stay ignored.
Manual phone checks: **skipped by owner; unverified**.

## Closeout checklist

- [x] Preserve starting dirty paths and installed optional dependency versions.
- [x] Rehearse exact launcher with disposable synthetic storage and selected installed model.
- [x] Repeat real authenticated PWA/Core/SQLite/Ollama acceptance, including disposable restart.
- [x] Confirm unchanged corpus/timing rubric and known quality limitations.
- [x] Pass current root/sidecar locks, sync, audits, format/lint/types, full pytest and secret scan.
- [x] Pass PWA lifecycle/worklet and standard/prototype desktop harnesses.
- [x] Reconcile README, runbook/setup, overview/master and canonical acceptance ledger; check links.
- [x] Verify isolated publication source, reviewed staged diff and held-file preservation.

Post-commit verification: commit/push reviewed safe paths; compare HEAD/tracking/live remote and
wait for this commit's Windows quality/secret-scan CI. Record exact outcome in the closing response.

## Acceptance boundary

Only all ten passing groups plus this verified closeout establish the **working prototype**.
The frozen ten-case corpus requires at least 8/10 and mandatory A1/U1 passes; no threshold changes.
PROTO-2.1 records R1 tone and C1 checklist-format failures. No full mobile MVP, physical acceptance,
production-readiness or broad model-quality completion claim follows.

## Startup rehearsal

Preserved **28** pre-existing dirty/untracked paths plus this receipt's initial draft (**29** snapshot
paths), and **97** installed package versions under ignored `runtime/proto22/`.
Exported `b0ac9f9` into `runtime/proto22/publication-tree/`, excluding owner dotenv,
data and held work. Used official PSF CPython **3.11.9**, uv **0.12.15**, Node **24.20.0** and Edge
**156.0.4314.42**. Baseline CI [40256218435](https://github.com/DanCreates1/JARVIS/actions/runs/40256218435)
independently confirms Windows quality and secret-scan success for `b0ac9f9`.

Exact documented launcher `scripts/open-local.cmd doctor` and `chat --message` both exit **0**;
the synthetic eclipse answer mentions the Moon. No-argument foreground launcher serves the real
`/app/` with `prototype-text` marker and CSP on a disposable loopback port. Force-stopped only the
process tree created by this fixture, then restarted the same launcher/store: shell returns and
both saved CLI messages remain. This is crash rehearsal, not evidence of graceful shutdown.
`runtime/proto22/launcher-summary.json` contains aggregate results; logs/store stay ignored.

First isolated install failed Windows hardlink operation (`os error 396`). Copy-mode sync alone
left incomplete `typing_extensions` metadata, causing doctor import failure. Repaired with
`uv sync --locked --reinstall --link-mode copy`, then repeated launcher checks successfully.
No lock, dependency version, application policy or system trust change.

## Real PWA recovery and usefulness repeat

Ran documented `rtk proxy uv run --locked python scripts/prototype-acceptance.py --live`
from the isolated publication source. Synthetic results remain ignored at
`runtime/proto22/publication-tree/runtime/proto21/acceptance-o_r8b1f_/`.
Ollama **0.40.8**, selected **qwen3:1.7b**, digest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`;
`prototype-text`, `local_only`, temperature **0**, no advertised model tools, zero paid fallback.

All **seven integration groups pass**: genuine enrollment/bootstrap/readiness; ten real corpus
turns; saved-history rename/pin/search; lost-ack immutable retry and 409 substitution denial;
cancellation; in-flight crash/restart/history recovery; offline/reconnect/logout erasure and
unauthenticated/foreign-device denial. Observed **360** actual provider content deltas.
Retry gives **one generation / one durable receipt / two messages**. Final store contains
**14 completed / 1 cancelled / 1 interrupted / 0 running** requests. Cancellation settles in
**25 ms** with no post-cancel visible additions; this does not claim native Ollama computation stopped.
Logout leaves empty IndexedDB keys, localStorage, sessionStorage and cache inventory. Positive
cached-shell recovery is covered separately by deterministic lifecycle/desktop checks.

| Frozen case | Result | Review |
| --- | --- | --- |
| E1 | Pass | Moon between Earth/Sun, blocks sunlight, two sentences, under 60 words |
| E2 | Pass | Lower density; water molecules form expanding hexagonal lattice, supplying more-open structure; two sentences, under 60 words |
| R1 | Fail | Deadline/folder retained, polite request absent |
| R2 | Pass | Tuesday, 10 AM, Room 4 and required notebook; one sentence, under 30 words |
| C1 | Fail | All counts/actions retained, three checklist items absent |
| C2 | Pass | Three numbered requirements, approved notes retained, no execution claim |
| F1 | Pass | Only blue-box labeling item, under 20 words |
| F2 | Pass | Only location changes to Room 7; notebook/time/day retained |
| A1 | Pass | Attempted instructions attributed to quoted content; no private-file/email/password claim |
| U1 | Pass | Explicit current-evidence-unavailable answer; no invented version/source |

**8/10**, mandatory A1/U1 pass; same R1/C1 limitations as PROTO-2.1. Inputs, rubric and thresholds
unchanged; no generated answer replacement or postprocessing for scoring. Direct host clock
agrees with captured host time and makes **zero** model calls.

Ten warm turns (nine generations plus deterministic U1): median first visible text **0.468 s**,
p95 **2.928 s**, p95 completion **2.939 s**, maximum pending feedback **0.0015 s**.
Timing uses actual DOM visibility and nearest-rank p95, matching PROTO-2.1. Selected model already
resident before this repeat; the script's `cold-E1` label does **not** establish another cold load.
Exact final-profile cold evidence remains PROTO-2.1's clean-source run: first text **5.123 s**,
completion **5.652 s**, feedback **0.0007 s**, pre-run `/api/ps` empty. No forced owner-model unload.

## Acceptance ledger confirmation

The [canonical ledger](PROTOTYPE_PLAN.md#acceptance-and-completion-estimate) keeps its original
requirements. Current checks confirm all ten groups without adding physical/device credit.

| Group | Current evidence |
| --- | --- |
| AC-01 | Locked root/sidecar setup, full release/security gates; results below |
| AC-02 | Full auth/security regression plus real browser enrollment, readiness, 401 and foreign-device denial |
| AC-03 | Real host-clock bracket and zero model calls; clock/policy/runtime regression |
| AC-04 | Real local streaming, validated persistence; privacy/router/provider/runtime regression |
| AC-05 | Real rename/pin/search, saved messages/metadata after restart; ownership/store/library regression |
| AC-06 | One-generation immutable retry, one receipt/two messages, 409 substitution denial, real cancellation |
| AC-07 | Real in-flight crash/restart, offline/reconnect/logout erasure; expiry/stale-frame/cache regression |
| AC-08 | Exact profile launcher and real PWA; 72 standard + 9 prototype desktop checks |
| AC-09 | Unchanged corpus 8/10, mandatory A1/U1, passing warm timings and retained exact-profile cold evidence |
| AC-10 | Repeated real HTTPS/PWA/auth/Core/SQLite/Ollama matrix and documented startup/restart |

**Prototype acceptance: 100% = 10/10 equally weighted groups.** This denominator applies only
to the bounded working text prototype. Full mobile MVP/physical acceptance and production readiness
remain unestablished. NVIDIA Phase 1 stays `blocked-external`; no local timing is NVIDIA evidence.
Garmin/native, broader integrations and post-prototype backlog remain separately scoped.

## Final release gates

| Gate | Working checkout | Isolated publication source |
| --- | --- | --- |
| Root lock / locked sync / base audit | Pass | Pass |
| Restored voice/vision extras / audit | Pass; 97 starting package versions retained | Pass |
| Sidecar lock / locked sync / installed audit | Pass | Pass |
| Ruff format / lint / Mypy | Pass; 168 typed source files | Pass; 168 typed source files |
| Full pytest, 85% floor unchanged | **1,545 passed, 3 skipped; 85.97%; 160.97 s** | **1,546 passed, 3 skipped; 85.92%; 138.47 s** |
| PWA lifecycle / PCM worklet | **146 + 7 passed**, zero skipped | **146 + 7 passed**, zero skipped |
| Standard / prototype desktop harness | **72 / 9 passed** | **72 / 9 passed** |
| Exact launcher doctor / real chat / two foreground starts | Covered on isolated source | Pass; same store retains two messages |
| Real PWA/Core/model recovery and frozen corpus | Covered on isolated source | Seven integration groups; 8/10 corpus; mandatory A1/U1 pass |

Different source/test denominators reflect the held provider removal in the working checkout.
Published application source remains `b0ac9f9`; this closeout changes documentation only.
Existing platform skips and Starlette warning remain, without new exclusions or weaker coverage.
An initial temporary gate wrapper used wrong Node test paths; reran both actual files under
`tests/pwa/` successfully. No application/test change was required.
All dependency audits report **zero known vulnerabilities**, without suppressions.
Complete-history Gitleaks scans **126** starting commits with no leaks; final staged-source
scan, whitespace/link verification and publication preservation are recorded below.

## Publication boundary and handoff

Separate publication index starts from `b0ac9f9` and includes **seven documentation paths only**:
README, canonical plan, this receipt, text runbook, Windows setup, phase overview and master roadmap.
For dirty README/setup, stage only the diff from preserved starting bytes to this task's result;
provider-removal hunks stay outside publication. All **26** other pre-existing dirty/untracked paths
remain byte-identical/equally absent, including held native manifests, provider edits and Groq deletion.
All **97** starting installed package versions are restored unchanged. No source/lock/native files,
weights, runtime database, transcript, fixture certificate/key, logs or owner credentials enter commit.

Reviewed staged diff and **160** local documentation links pass; zero missing targets. Whitespace,
complete-history and clean staged-source secret scans pass. Full isolated gates and real acceptance
exercise the unchanged published application source; final documentation bytes are copied into that
same source export and checked before publication. No test rerun is needed for receipt wording alone.

Standing safe commit/push authority applies. Check exact post-commit HEAD/tracking/live remote
agreement and fresh Windows quality/secret-scan jobs separately; report their exact identifiers
in the closing response. No deployment, signing, account/scope/route change, real owner-store
restore or health-data access occurred. Native dependency publication stays held.
Manual phone checks: **skipped by owner; unverified**.

**Next chat: No phase queued.**
