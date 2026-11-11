# Groq deferred — 2026-10-21

Owner requested removal for now, with a record for possible future use.
Removed the provider adapter, bootstrap and diagnostics registration, credentials,
model settings, activation examples, and Groq-only tests. Shared HTTP error mapping
now lives in `src/jarvis/llm/http_errors.py` for NVIDIA and Gemini.
FAST/PRIMARY role identifiers remain provider-neutral; unbound roles use existing
local fallback. No replacement cloud provider was enabled.

Groq was optional responsive cloud inference for public requests, never required
for JARVIS. It was inactive when removed: no configured API key. This removal
does not revoke credentials or change any provider account.

Official documentation reviewed on 2026-10-21:

- [Free limits](https://console.groq.com/docs/rate-limits): GPT-OSS 20B listed
  30 requests/minute, 1,000 requests/day, 8,000 tokens/minute, 200,000 tokens/day.
  Limits apply per organization; exceeding limits returns HTTP 429.
- [Billing](https://console.groq.com/docs/billing-faqs): Developer tier is paid;
  upgrading requires a payment method.
- [Model catalog](https://console.groq.com/docs/models): availability changes;
  the former Qwen 3.6 preview selection must not be assumed available.

Future reconsideration: useful for occasional fast public inference, limited for
sustained long-context agent work. Recheck models, quotas, billing and data terms;
retain $0 policy, privacy routing, approvals and local fallback. Restore code from
Git history only after review; this record does not authorize activation or login.
Historical phase reports and dated provider decisions remain evidence, not current
setup instructions.

Validation: locked resolution/sync, Ruff format/lint, mypy and Gitleaks passed.
Full pytest: 1,532 passed, 3 skipped; 85.95% coverage (85% gate). The added
legacy-environment regression also passed in the targeted 23-test settings run.
Dependency audit failed on 30 advisories in unchanged locked certifi, Pillow and
pypdf versions. Publication remains held pending that automated security gate;
unrelated held native dependency edits are excluded from this work.
