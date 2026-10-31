# Public research

Current Phase 11 capability: explicit `public-research` on the existing Windows Core/PWA.
[Completion evidence](phase-reports/current/PHASE_11_COMPLETION.md), closed 2026-10-31.
Run `scripts\open-research.cmd` or `scripts\open-research.cmd doctor`. Stop an existing Core by
its normal owner-controlled shutdown before starting another writer. This launcher uses the
installed `qwen3:1.7b` for ordinary local chat; no download or cloud fallback. Original
`prototype-text`, daily and private profiles keep their existing feature boundaries.

## Available workflow

Use a self-contained public request beginning with `Research` and include up to four explicit
public HTTPS source URLs, for example:

```text
Research current Python macOS installer certificates and SQLite Windows support at https://www.python.org/downloads/ and https://www.sqlite.org/changes.html
```

Only the current public request selects sources. Prior chat, memory, attachments, personal data and
credentials never become search queries. Explicit source selection performs no discovery request.
It uses the existing bounded search port, pinned public-DNS fetcher, redirect policy, isolated
HTML/text/PDF parser, extractive synthesizer and exact-span citation validator. Source-body links
are never crawled. Private/uncertain requests fail closed; authenticated URLs, query parameters,
direct IPs, local/private networks, non-HTTPS sources and excessive sources are denied. Fragment
identifiers are stripped before acquisition. No login/paywall workaround is provided.

Current research replies are bounded **source excerpts**, with nearby clickable URLs, retrieval
timestamps, explicitly unknown publication dates, expiry and unresolved questions. These are source
statements, not an independent truth check or a promise to answer every question. Extractive
selection can be incomplete or poorly relevant; it does not infer current release versions from
old release listings or reconcile different claims. Distinct sites do not establish independent
publishers or consensus. Subdomains collapse conservatively for the existing diversity check.
Use exact source links to inspect context. Browser rendering treats source text as inert text.

No second model rewrites these replies. A failure produces deterministic current-evidence
unavailable, without model-generated current facts or citations. Freshness is checked against
the current clock and the oldest source expiry (default **3600 s**), never against a report's own
generation time. Future timestamps, expired/inactive sources and wrong-host evidence fail closed.
Publication time and current retrieval time remain different facts.

## Discovery status

Without explicit URLs, existing `JARVIS_RESEARCH_SEARCH_PROVIDER=wikimedia` uses the unchanged
`https://en.wikipedia.org/w/api.php` endpoint. The 2026-10-28 and 2026-10-31 production-fetcher probes still
return normalized **`authentication_required`** (HTTP access denial). Legacy C's 2026-10-02
blocker remains. Successful direct official-source reads do not clear that discovery blocker.
Queries requiring discovery therefore return unavailable on this configuration.

Optional `searxng` uses the existing HTTPS JSON search port and requires an explicitly reviewed
endpoint. No instance was selected, authenticated or activated. The official
[SearXNG search API](https://docs.searxng.org/dev/search_api) documents JSON support and public
instances disabling formats; an arbitrary public instance is not an accepted substitute.
[MediaWiki search](https://www.mediawiki.org/wiki/API:Search) documents the retained search API.
These primary contracts were checked 2026-10-28; they do not prove local endpoint availability.

## Privacy, storage and authority

This profile forces local-only models, loopback Core and $0. PWA files, health and memory-review
entry points, coding, email, voice, Windows actions and background integrations remain disabled.
Existing daily-text local recall and trusted-local controls retain their original boundaries.
Existing PWA application authentication, scopes, ownership, CSRF, replay and cancellation controls remain.
No new enrollment or production scope follows from profile selection. Automated acceptance uses
disposable synthetic identities/state only. Optional cloud in historical standard mode retains
its existing current terms/free-capacity and full-context privacy gates; none is qualified here.

Acquired source bodies, pending research reports and evidence projections stay volatile. They are
not automatically written to the research ledger or trusted memory. Canonical conversation history
still stores the user's request and final cited reply under existing ownership/retention policy;
**volatile research does not mean ephemeral conversation history**. PWA persists no source text,
query or reply in browser caches/storage. Saved conversation replies do not refresh themselves.
Send a new request to retrieve again; retrying the same accepted request returns its receipt.

Existing explicit `research run --store` and trusted local review remain separate exact,
digest-bound, expiring, one-use approvals. Source/model text never grants that approval. Existing
source deletion is transitive; inspect/export before an expressly authorized delete. Parser text
changes create new immutable source versions even when raw bytes match, preserving old locators
and staling their claims. No schema migration or automatic trusted-memory promotion was added.

## Bounds and recovery

Automatic runs retain one query, at most four sources/eight fetches, twelve claims, 30000 chars per
source, 100000 total source chars, 45 s total and 20000 chars per projection/reply. Quotes remain
at most 25 words per source. Fetch/parser limits, media allowlists, cancellation and fail-closed
SSRF protections remain authoritative. Parsing is a bounded child process, not an OS sandbox.
No JavaScript rendering, authenticated sources, crawling, background refresh or offline web cache.

Locked PDF parser minimum is `pypdf>=6.21.4,<7` after 2026-10-31 security revalidation.
Use locked setup to apply the reviewed patch; do not downgrade to recreate the earlier audit.
The [official 6.21.4 release](https://github.com/py-pdf/pypdf/releases/tag/6.21.4) records its
security repairs. Other 96 starting package names/versions and the sidecar lock remain unchanged.

For research failure, check connectivity and public source accessibility, then issue a new explicit
request. Never add credentials or weaken DNS/TLS/privacy checks. For local chat-only recovery,
stop Core normally and use `scripts\open-daily.cmd` or `scripts\open-local.cmd`; approved ledgers
remain inspectable through existing local commands. Restart marks interrupted receipts honestly
and never silently repeats acquisition. Browser logout erases displayed research/history/drafts.

Opt-in current live acceptance:

```powershell
rtk proxy uv run --locked python scripts/research-acceptance.py --live
```

It uses disposable loopback TLS, synthetic application identity/store, real public-source requests
and a headless desktop browser. It verifies exact spans, citations, replay, fresh retrieval after
restart, unavailable discovery, browser erasure and zero model/research-ledger/memory writes.
Raw public-source/browser evidence stays ignored under `runtime/phase11/`. Ordinary CI remains
network/model/device-free. Physical phone checks **skipped by owner; unverified**. No native,
physical/mobile MVP or production acceptance inferred; native/provider publication holds remain.
