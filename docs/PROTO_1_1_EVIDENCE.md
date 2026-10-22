# PROTO-1.1 dependency/security evidence

Date: **2026-10-22**. Starting branch/HEAD: `main`, `fb5ef47`.
Scope: restore mandatory Python dependency/security baseline; stop before PROTO-1.2.
Canonical scope and acceptance: [Prototype Plan](PROTOTYPE_PLAN.md).

## Dependency result

| Package | Starting version | Accepted version | Change |
| --- | --- | --- | --- |
| certifi | 2026.7.22 | **2026.10.19** | Root and Garmin locks; remove compromised CA trust described by upstream |
| pypdf | 6.19.0 | **6.21.2** | Root lock and minimum `>=6.21.2,<7`; includes current parser security fixes |
| Pillow | 12.3.0 | **13.0.0** | Root lock and constraint `>=13,<14`; fixes audited native/image/parser vulnerabilities |

Fresh starting audit reproduced **44 root advisories**: certifi 1, Pillow 35, pypdf 8.
The sidecar's starting certifi advisory was `PYSEC-2026-4320` / `GHSA-6q48-6c7w-9gw2`.
Final root base audit (69 packages), root with restored extras (97 packages), clean publication
base (69 packages), fresh sidecar (16 packages), and existing sidecar site-packages (16 packages)
all report **zero known vulnerabilities**, with no skipped packages or advisory suppressions.
This is a dated audit result, not a guarantee against future findings.

Only three third-party package entries changed in the root lock, plus this project's matching
dependency metadata. Only certifi changed in the sidecar lock. No package added or removed;
no audit/coverage/security gate lowered. Garmin direct dependencies remain unchanged.

Primary sources reviewed on the evidence date:

- [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
  and [2026.10.19 metadata](https://pypi.org/project/certifi/2026.10.19/).
- [pypdf changelog](https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html) and
  [6.21.2 metadata](https://pypi.org/project/pypdf/6.21.2/). This release additionally bounds xref
  table size and repeated file loading beyond the starting audit's minimum fix suggestions.
- [Pillow 13.0.0 security and compatibility notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
  and [release metadata](https://pypi.org/project/pillow/13.0.0/).

Pillow drops Python 3.10; this project already requires Python >=3.11,<3.13. Lock includes
Windows CPython 3.11/3.12 wheels. Production consumers use restricted PNG/JPEG open/load,
RGB conversion, thumbnail/JPEG encoding and `ImageGrab.grab`; none use the removed APIs.
pypdf readers, filter bounds and text extraction remain source-compatible. Existing malformed,
encrypted, oversized, image-bomb, animation, MIME-spoofing, timeout, cancellation, credential-
isolation and protocol tests passed. No compatibility-driven application or test edit needed.
Tests used synthetic fixtures; no owner files, camera, screen or health data processed.

## Verification

Commands run through RTK, using locked dependencies. Root runtime: CPython **3.11.9**;
isolated sidecar: CPython **3.12.14**; uv **0.12.15**.

| Gate | Result |
| --- | --- |
| Root lock check / locked base sync | Pass; 119 packages resolved |
| Fresh sidecar lock check / locked sync | Pass; 20 resolved, 16 installed |
| Root Ruff format / lint / Mypy | Pass; 435 files checked for format, 168 source files typed |
| Root full pytest, with preserved provider edits | **1,533 passed, 3 skipped; 85.95% coverage; 132.18 s** |
| Focused parser/hostile attachment/vision regression | **49 passed** |
| Publication snapshot Ruff format / lint / Mypy | Pass; 434 files checked for format, 168 source files typed |
| Publication snapshot full pytest | **1,534 passed, 3 skipped; 85.90% coverage; 136.76 s** |
| PWA lifecycle and PCM worklet | **152 passed; 0 skipped** |
| Desktop browser harness | **72 cases passed**, keyboard/history/named log and contrast assertions |
| Root / sidecar vulnerability audits | Pass, as detailed above |
| Windows bootstrap | Pass using `rtk proxy pwsh -NoProfile -File scripts/bootstrap.ps1` |
| Gitleaks history | Pass; 123 starting commits, no leaks; publication scan recorded before commit |
| Whitespace / document links / held-file preservation | Verified before publication |

The first exported-snapshot pytest attempt failed because its relative temporary directory's
parent did not exist (`WinError 3`); the failed coverage result is not acceptance evidence.
The complete retry uses a fresh absolute base under the original ignored `runtime/proto11/`.
No test or coverage requirement was disabled for that accepted full run. Existing Starlette
deprecation warning and optional/platform skips remain explicit.

Generated sidecar interpreter shim is blocked by App Control (`4551`). An explicit existing
CPython 3.12.14 executable and `UV_PROJECT_ENVIRONMENT` pointing at ignored
`runtime/proto11/garmin-venv` allowed fresh locked sync/check. Existing sidecar site-packages
were synchronized from `uv export --locked --no-dev` using `uv pip sync --require-hashes
--target garmin_sync/.venv/Lib/site-packages` and that interpreter; only certifi changed.
Both environments audited clean. No Windows security policy changed. Legacy Windows PowerShell
blocked script execution; existing PowerShell 7 ran the bootstrap successfully.

Root base sync temporarily removes extras. `uv sync --locked --extra voice --extra vision
--link-mode copy` restored them. Full installed-package comparison against the starting snapshot:
no missing/additional package, only the three accepted version changes. No live voice/capture run.

## Publication and remaining boundaries

Working tree began with **34 dirty paths**, including unpublished planning, provider changes and
held native manifests. Original planning snapshots under ignored `runtime/proto-audit/` isolate
12 top-of-document planning banners from earlier provider/document edits. A separate index builds
the reviewed publication tree from HEAD plus those banners, prototype documents, dependency files
and this evidence. Exported clean source is tested independently of unpublished provider changes.
No bare global staging; no runtime evidence, generated environment or private configuration staged.

Held `mobile/package.json` SHA-256 remains
`f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`;
`mobile/package-lock.json` remains
`acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`.
Native audit remains held on the previous **51 findings (45 high, 6 moderate)**; no native repair
or new native acceptance claimed. Provider edits, Groq deletion and older shared-document changes
remain in the working tree, excluded from publication and byte-preserved.

AC-01 earns 1/1; prototype estimate becomes **75% = 7.5/10** acceptance groups. Integrated live
model quality and real PWA/Core/Ollama proof remain open. No prototype/MVP/production completion,
new enrollment, route change, health access or deployment claimed. Manual phone checks remain
**skipped by owner; unverified**. **PROTO-1.2 not started.**
