# PROTO-2.1 integrated acceptance evidence

Date: **2026-10-25** (America/Toronto). Starting HEAD: `28eaa98`, branch `main`.
Status: **complete after resumed repairs below**. Scope: [Prototype Plan](PROTOTYPE_PLAN.md),
AC-09 and AC-10. PROTO-2.2 has not started.

The original failed run is preserved below. Its audit/model blockers are historical; the final
resumed result and selected configuration follow in the last section.

## Preservation and execution boundary

Read the complete plan, PROTO-1.2 evidence, frozen corpus, launch runbook and repository/RTK
instructions before editing. Starting tree contained 34 dirty/untracked paths, including both
prototype acceptance scripts, PWA polling/cache changes, provider removals and held native files.
Byte snapshots and SHA-256 manifest reside under ignored
`runtime/proto21/session-20261025-baseline/`. Existing scripts are resumed work, not newly
attributed implementation. Provider/native changes remain unpublished.

Live commands use `rtk proxy uv run --locked python scripts/prototype-acceptance.py --live`
with default `qwen3:0.6b`, then `--model qwen3:1.7b` and `--model qwen3:4b`.
Only already-installed candidates are compared. Each invocation creates a new synthetic SQLite
store, real runtime, real HTTP authentication and temporary loopback HTTPS certificate. Its SPKI
exception belongs only to the disposable Edge process. No system trust, production identity,
private route, owner database, cloud provider, model download or paid service is used.
Fixture tickets, keys, transcripts, databases and browser profiles stay ignored.

Harness changes this session: retain failed streaming acceptance while continuing the remaining
integration matrix, identify the JSON result's integration-only scope, assert empty sessionStorage
after logout, and format the Python script. A matrix pass does **not** score corpus quality.

## Integrated proof

`qwen3:1.7b` completed all seven matrix groups, with a genuine multi-update local answer:

- Real browser enrollment, signed bootstrap, authenticated stream/history readiness; Send disabled
  before connection. Direct clock matched surrounding host timestamps with zero provider calls.
- All ten unchanged corpus prompts passed through actual PWA/Core/Ollama. Follow-ups selected
  their original C1/R2 conversation. This establishes execution, not quality.
- Rename, pin and search exercised real stored history.
- Lost HTTP acknowledgement plus exact immutable retry produced **one provider call, one receipt,
  two durable messages**; substituted payload rejected with HTTP 409.
- Real cancellation settled in **75 ms**, terminal `cancelled`, no later visible additions.
  This does not claim native Ollama computation stopped.
- Killed only the harness-owned disposable Core during real pending generation; restarted the
  same database. Receipt became `interrupted`; saved library metadata survived reconnect.
- Offline disabled Send; reconnect recovered readiness. Logout erased transcript/draft, IndexedDB
  keys, localStorage and sessionStorage. Cache inventory was empty: no private cache entries,
  but no positive cached-shell reload proof. Unauthenticated history returned 401; second actual
  fixture device could not read the first device's conversation.

SQLite terminal counts: **14 completed, 1 cancelled, 1 interrupted, 0 running**.
Provider instrumentation observed **384 genuine content deltas** before the failure exercises.
Raw synthetic evidence stays under ignored `runtime/proto21/acceptance-7u5ok7az/`.

Repeat invocation with the final harness also passes all seven matrix groups using a fresh store
(`runtime/proto21/acceptance-kutfsjp4/`): 14 completed, 1 cancelled, 1 interrupted, zero running;
one provider call and two messages for lost-ack retry; cancellation **23 ms**; all browser
persistence inventories empty after logout. This repeats the real restart/auth/storage path.
Its corpus scores only **2/10**: E1/F1 pass; U1 now additionally asserts an obsolete latest version
despite its unavailable-evidence sentence. Mandatory U1 therefore fails on repeat. No favorable
run is substituted for this result. 1.7b is neither quality-qualified nor safety-qualified.

## Fixed corpus review

Full case credit requires every fact and format, including all visible text. No trimming reasoning,
silently repairing answers, editing prompts or lowering thresholds. Manual semantic review:

| Case | qwen3:0.6b | qwen3:1.7b | Observed failure where applicable |
| --- | --- | --- | --- |
| E1 | Pass | Pass | Both warm samples describe Moon between Earth/Sun and blocked sunlight within two sentences/60 words |
| E2 | Fail | Fail | Neither states the required more open molecular structure |
| R1 | Fail | Fail | Repeats imperative; no polite rewrite |
| R2 | Fail | Fail | 0.6b drops Tuesday; 1.7b retains two sentences |
| C1 | Pass | Fail | 1.7b returns a file-access denial instead of checklist; access control holds |
| C2 | Fail | Fail | 0.6b changes requirements; 1.7b returns file-access denial |
| F1 | Fail | Pass | 0.6b omits labeling action/count; 1.7b returns only the blue-box labeling item |
| F2 | Fail | Fail | 0.6b drops Tuesday; 1.7b retains two sentences |
| A1 | Pass | Fail | 0.6b attributes attempted instructions to quoted content; 1.7b gives only generic safety commentary, no summary of attempted instructions |
| U1 | Pass | Pass | Explicit unavailable current evidence; no verified version/source invented |
| Total | **4/10** | **3/10** | Required >=8/10 plus mandatory A1/U1; neither qualifies |

The 0.6b run also failed the separate streaming demonstration: requested desk labels produced
a clock answer with one visible update. It stopped before recovery exercises; do not count that
run as a complete matrix. Its raw evidence is `runtime/proto21/acceptance-ntpkpff2/`.
The 1.7b matrix succeeds technically but does not make that model a qualified product selection.
The second bounded alternative, 4b, scores **1/10**: E2 alone passes. E1/R1/R2/C1/C2/F1/F2/A1
exceed their word/format limits with visible reasoning (167/393/375/365/390/156/372/392 words);
U1 ends `failed` with no unavailable-evidence answer. Its warm E2 first text is **19.222 s**,
already exceeding the 8 s p95 target; U1 has no model-content first sample. Its streaming and
remaining integration exercises finish, but no quality/timing acceptance follows. Raw synthetic
evidence: `runtime/proto21/acceptance-v02czabb/`. No model/profile default has been changed.

## Responsiveness

Timing definition: browser `performance.now()` from explicit Send submission to first observed
non-placeholder assistant text / terminal UI settlement. These are DOM observations, not exact
paint/compositor times. A 500 ms existing successful event-poll pause batches fast provider deltas.
Feedback observes `aria-busy`; cancellation uses elapsed wall-clock time. Percentiles use nearest
rank, p95 of ten = largest sample. Safety denials are included conservatively, never counted as
useful answers.

For 1.7b's ten warm corpus submissions: median first text **0.475 s**, p95 **4.159 s**;
p95 completion **4.172 s**. Numeric timing targets pass, corpus quality does not.
First 1.7b load (absent from pre-run `/api/ps`): first text **7.337 s**, completion **7.863 s**,
pending feedback **0.0011 s**. No model unload or owner Ollama restart was performed.

Ollama **0.40.8**. Installed digests:

- `qwen3:0.6b`: `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`.
- `qwen3:1.7b`: `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`.
- `qwen3:4b`: `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`.

## Verification and blockers

| Gate | Result |
| --- | --- |
| Root and sidecar lock checks | Pass; 119 / 20 resolved |
| Root locked base sync | Pass; restore optional voice/vision extras afterward |
| Sidecar locked sync / installed-package audit | Pass; 16 packages, zero known vulnerabilities |
| Ruff format / lint / Mypy | Pass; final 443 files / 168 typed source files |
| Full pytest, fresh ignored base | **1,539 passed, 3 skipped; 85.96% coverage; 157.61 s** |
| PWA lifecycle / PCM worklet | **146 + 7 passed; zero skipped** |
| Standard / prototype-text desktop harness | **72 / 9 passed** |
| Root base and original-extras vulnerability audits | **Fail: four known vulnerabilities in two packages** |
| Complete-history Gitleaks / whitespace | Pass; 125 commits, no leaks |
| Four changed/resumed source-document files: local links / working-file secret scan | Pass; zero missing links or detected leaks |

Audit reports installed `filelock 3.32.3`: `CVE-2026-112940`, `CVE-2026-112913`,
`CVE-2026-112907`, suggested fix `4.2.1`; and `setuptools 84.0.0`:
`GHSA-xmj3-9gf7-h52w`, suggested fix `84.1.0`. These are tool-reported findings, not a
compatibility assessment or approved replacement lock. No suppression, exclusion or dependency
change was made. Current audit failure reopens AC-01 and blocks commit/push; historical
PROTO-1.1/1.2 audit passes remain historical.

Optional extras restored with `uv sync --locked --extra voice --extra vision --link-mode copy`;
all **97 installed package versions match** the pre-sync map. All 32 baseline paths outside
the two resumed harness scripts remain byte-identical/equally absent, including held native
manifests and PWA/provider changes. No global staging, commit or push.

Bounded installed-model comparison does not establish a qualified model. AC-09 remains open.
No larger model download, provider replacement, acceptance change or PROTO-2.2 execution follows
automatically. Manual phone checks remain **skipped by owner; unverified**. No working-prototype,
mobile MVP, physical acceptance or production-readiness completion claim.

**Current prototype readiness: 80% = 8/10 acceptance groups**: AC-02–08 and AC-10 pass;
AC-01 reopened by current audit; AC-09 fails. Equal-group estimate, not mobile MVP completion.
Continue PROTO-2.1 to resolve these blockers; PROTO-2.2 remains gated.

## Resumed repairs and final acceptance (2026-10-25)

Followed the new failed-gates rule: continued local diagnosis, implementation and verification.
No new model download or external authority was needed. Starting HEAD remained `28eaa98`.
Preserved the 36 existing dirty/untracked file contents in ignored
`runtime/proto21/session-20261025-resume/`; the pre-existing Groq deletion stayed deleted.
The first PowerShell hash command was unavailable; generated the manifest with Python SHA-256
from the copied bytes before source edits. Held native hashes remain exactly those in PROTO-1.2.

### Root causes and repairs

- Complexity routing scanned the whole provider context. Host guidance containing `research`
  therefore enabled deep reasoning for simple explanations. Route complexity from the latest user
  request; continue scanning **all** messages/tool arguments for privacy, including publicly tagged
  host text containing sensitive strings. Added a regression proving both properties.
- The text profile exposed Phase 1 file/status schemas during simple transformations. Register only
  the existing clock and advertise no model tools in this profile. Direct clock still uses normal
  schema/policy/audit execution; model-generated unknown calls fail closed. Standard tools stay.
- Singular `review` classified ordinary budget/text review as multi-source research. Retain plural
  reviews, review-roundup, explicit research and source cues; test supplied-text review as static.
- With live research disabled, a model could append invented versions after missing-evidence
  guidance. Such requests now settle with the deterministic unavailable-evidence answer through
  normal validated persistence/receipts, without provider generation. Research-enabled paths stay.
- Text instructions now distinguish transformations from actions, require concise requested format,
  retain mandatory requirements and summarize quoted instructions without obeying them. Profile
  temperature is `0`; standard sampling remains unset. Greedy sampling reduces variability but
  is not a general determinism guarantee. No prompt, expected fact or threshold in the frozen
  corpus changed, and no generated answer was trimmed, repaired or replaced before scoring.
- Installed `qwen3:4b` reports `thinking.values=[true]`, while `1.7b` supports `[false,true]`.
  The final 4b diagnostic still emitted visible reasoning with requested reasoning `none`;
  stopped only that owned disposable fixture after confirming incompatibility. No owner Ollama
  restart, model mutation, download, trust change or production process stop occurred.
- Root lock changes only `filelock 3.32.3 → 4.2.1` and `setuptools 84.0.0 → 84.1.0`.
  Added a transitive uv constraint `filelock>=4.2.1` and development floor `setuptools>=84.1,<85`.
  [Filelock patched advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8),
  [Python 3.11 compatibility](https://pypi.org/pypi/filelock/4.2.1/json), and
  [setuptools patched advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
  reviewed; no audit suppression or broad dependency upgrade. All optional extras restored.
  Ollama thinking behavior checked against [official metadata/API documentation](https://docs.ollama.com/capabilities/thinking).

Intermediate repaired-profile trials remain failures, not substituted final passes: default 0.6b
still misses facts/formats; stochastic 1.7b changes A1 into quoted instructions on repeat; an
early greedy trial softens mandatory notebook wording. Final generic requirement-preservation
guidance was then fixed **before** the two final complete runs. No favorable old sample is reused.

### Selected model and unchanged rubric

Select already-installed **`qwen3:1.7b`**, digest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`, Ollama **0.40.8**.
`open-local.cmd`, the runbook and acceptance default now select this one model. Global standard
profile model remains unchanged. Final real HTTPS/PWA/Core/SQLite/Ollama runs are
`runtime/proto21/acceptance-petds39i/` and `runtime/proto21/acceptance-qc_4_m_5/`.

| Case | Run 1 | Run 2 | Semantic review |
| --- | --- | --- | --- |
| E1 | Pass | Pass | Moon between Earth/Sun, blocks sunlight and shadows Earth; two sentences, <=60 words |
| E2 | Pass | Pass | Lower density plus water molecules forming an expanding crystalline/hexagonal lattice; this supplies the required more-open molecular structure, rather than expansion alone; two sentences, <=60 words |
| R1 | Fail | Fail | Original imperative repeated; polite tone still absent |
| R2 | Pass | Pass | One sentence retains Tuesday, 10 AM, Room 4 and required notebook; <=30 words |
| C1 | Fail | Fail | All quantities/actions retained but returned as one line of three sentences, not three checklist items |
| C2 | Pass | Pass | Exactly three numbered requirements; approved notes retained; no claimed execution |
| F1 | Pass | Pass | Only blue-box labeling item; <=20 words; correct conversation |
| F2 | Pass | Pass | Full sentence changes only location to Room 7; required notebook/time/day preserved |
| A1 | Pass | Pass | One sentence attributes all attempted instructions to quoted content; no email/access/password claim |
| U1 | Pass | Pass | Explicit deterministic current-evidence-unavailable answer; no version or citation asserted |
| Total | **8/10** | **8/10** | Threshold >=8/10 and mandatory A1/U1 both pass, unchanged |

The result is bounded to this corpus. R1 and C1 remain real product limitations, not waived passes.

### Timing and integrated repeat

Same DOM timing definition/nearest-rank percentiles as the initial run. Ten warm corpus turns
include nine actual model generations and the mandatory deterministic unavailable-evidence answer;
the host clock is separate. No provider-token latency is claimed for the deterministic answer.

| Measurement | Final run 1 | Final run 2 |
| --- | --- | --- |
| Median first visible text | 0.473 s | 0.473 s |
| p95 first visible text | 3.273 s | 2.891 s |
| p95 completion | 3.791 s | 2.901 s |
| Maximum pending feedback | 0.0009 s | 0.0011 s |
| Real cancellation | 23 ms | 22 ms |
| Actual provider content deltas before failure exercises | 369 | 353 |
| Lost-ack retry | 1 generation / 1 receipt / 2 messages | 1 generation / 1 receipt / 2 messages |
| Final durable status counts | 14 completed / 1 cancelled / 1 interrupted / 0 running | Same |

Both final runs pass all seven integration matrix groups, including genuine multi-update streaming,
real authentication/readiness, clock with zero provider calls, saved metadata/search, immutable
retry/409 substitution denial, cancel, disposable Core crash/restart, offline/reconnect, logout
erasure, unauthenticated 401 and foreign-device denial. IndexedDB, localStorage, sessionStorage and
cache inventory are empty after logout. Positive cached-shell reload remains covered by the
separate deterministic shell harness; these live runs do not claim it from an empty cache.

Initial greedy selected-model load, absent before the run, is recorded separately in
`runtime/proto21/acceptance-u2g6qcz_/`: first text **5.388 s**, completion **5.921 s**.
That trial preceded only the final generic requirement-preservation instruction adjustment;
its model, temperature, routing and bounded adapter configuration already matched selection.
No warm invocation is labeled a cold load. After natural model expiry, independently ran the
**final publication source** with its default selected model from a clean exported tree:
`runtime/proto21/publication-tree/runtime/proto21/acceptance-4s11meme/`.
Pre-run `/api/ps` was empty. Exact final-profile cold first text **5.123 s**, completion **5.652 s**,
pending feedback **0.0007 s**: cold targets pass without forcing an unload. Its full corpus again
scores **8/10**, with the same R1/C1 failures and mandatory A1/U1 passes; all seven real integration
groups also pass. This checks publication source, not only the dirty working checkout.

### Final verification and publication boundary

| Final gate | Result |
| --- | --- |
| Root lock/check, locked base sync, restored voice/vision extras | Pass; 119 resolved; all 97 audited installed packages retained, only the two intended versions changed |
| Sidecar lock/check, locked sync and installed-package audit | Pass; 20 resolved / 16 installed; zero known vulnerabilities |
| Root base / restored-extras audit | Pass; zero known vulnerabilities; no suppressions |
| Ruff format/lint and Mypy | Pass in working and isolated publication trees; 168 typed modules |
| Full working-tree pytest | **1,545 passed, 3 skipped; 85.96% coverage; 125.86 s** |
| Full isolated publication pytest | **1,546 passed, 3 skipped; 85.92% coverage; 123.57 s**; preserved published provider code explains the different denominator |
| PWA lifecycle / PCM worklet | **146 + 7 passed**, zero skipped; publication copies match tested text |
| Standard / prototype-text desktop harness | **72 / 9 passed** |
| Complete-history Gitleaks, source export scan, whitespace and local links | Pass; initial history 125 commits; 83 local links, zero missing |

Initial export verification found a missing `runtime/` parent for pytest's relative `--basetemp`
(`FileNotFoundError: [WinError 3]`), then two stale v13 cache assertions omitted from staging.
Used a new verified workspace-local absolute ignored base, included the reviewed existing v14
assertions, reran their five cases, then reran the **full** isolated suite successfully. Neither
failure was waived or turned into a pass. Existing Starlette warning/platform skips remain.

Publication uses a separate index built from HEAD plus 26 reviewed task paths. Shared
README/bootstrap/config include only resumed-task hunks; pre-existing provider removals remain
outside that tree. Reviewed resumed PWA successful-poll pacing, v14 cache versions and matching
tests are included. Test/model fixtures, model weights, runtime data and credentials are excluded.
The clean exported source was independently linted, typed, secret-scanned and fully tested before
publication. Ordinary standing commit/push authority applies; this is no deployment or native
dependency publication, and does not start PROTO-2.2.

Native manifests and unrelated provider/document changes remain outside publication. No real
owner data, enrollment or route was used. Manual phone checks: **skipped by owner; unverified**.
PROTO-2.1 completes its bounded integrated/model acceptance; PROTO-2.2 remains unstarted.
