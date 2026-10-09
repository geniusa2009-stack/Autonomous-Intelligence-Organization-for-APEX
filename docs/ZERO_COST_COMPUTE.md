# ZERO-COST COMPUTE

`MAX_API_COST_USD = 0.00`, `PAID_FALLBACK_ALLOWED = false`, `AUTO_BILLING_ALLOWED = false`,
`AUTO_UPGRADE_ALLOWED = false`, `QUOTA_BYPASS_ALLOWED = false` are **constants** (`apex_one/core/policies/cost.py`).
Environment variables cannot relax them; `apex-one doctor` reports any attempt.

## ZeroCostFirewall decision table (all must hold for ALLOW)
1. Request carries no budget; global policy is $0.
2. Provider is free-tier/local.
3. Price is **known** to be zero: local/self-hosted/mock by construction; remote only with a fresh live $0 price
   observation (OpenRouter publishes prices) **or** a human attestation that the key's account has no billing
   (`apex-one providers attest <id>`). Any live non-zero observation blocks even an attested route
   ("provider changed price"). YAML `verified` flags never suffice for remote routes.
4. OpenRouter routes must be `:free` variants.
5. Production purpose needs a **verified** production licence; research purpose needs a licence that is not BLOCKED.
6. Production on a remote provider needs verified terms.
7. Private student data only to providers that allow it (local by default).
8. Estimated cost exactly 0.0.
Adapters call `ZeroCostFirewall.assert_allowed` immediately before any HTTP request (defence in depth).

## When free capacity runs out
The FallbackPlanner returns `LOCAL_FALLBACK` (APEX native engine), `WAIT` (≤ 60 s), `QUEUE` (longer) or
`DEGRADE` (metric becomes NOT_MEASURED). There is no PAY outcome. HTTP 402 removes a provider for the session;
HTTP 429 sets a cooldown. No account rotation, no account creation, no quota bypass.

## Mandatory tests
`tests/test_zero_cost.py`: paid primary, paid fallback after 429, provider changes price, quota exhausted
(self-imposed and provider-signalled), unknown pricing, unknown licence, budget-carrying request, unattested free
route, expired attestation, 402, private data, and an exhaustive sweep of every route in the shipped registry
(no remote route can be allowed without attestation; ALLOW ⇒ exactly $0).

## Providers
NVIDIA NIM, Groq, Gemini, OpenRouter, Cloudflare Workers AI, Hugging Face router, Ollama, llama.cpp, MLX,
vLLM, SGLang, self-hosted design endpoints, mock (tests only). `apex-one providers --probe` shows live status.
