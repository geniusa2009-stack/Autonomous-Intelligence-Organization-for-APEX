# Live Provider Report (Phase 14)

_Generated 2026-10-30 21:39 UTC by `apex-one reports build` from measured artifacts._

Statuses: LIVE_TESTED (a real structured task ran through the $0 firewall and returned output), LIVE_FAILED, CREDENTIALS_REQUIRED, NO_FREE_ROUTE, NETWORK_BLOCKED (egress proxy denied CONNECT), LICENSE_BLOCKED, UNKNOWN. A status is never inferred: rows without an executed call are not LIVE_TESTED.

| provider | model | status | structured task correct | latency | measured at | evidence |
|---|---|---|---|---|---|---|
| nvidia_nim |  | **NETWORK_BLOCKED** | — | — | — | egress proxy denied CONNECT to integrate.api.nvidia.com (403 Forbidden) |
| groq |  | **NETWORK_BLOCKED** | — | — | — | egress proxy denied CONNECT to api.groq.com (403 Forbidden) |
| gemini |  | **CREDENTIALS_REQUIRED** | — | — | — | reachable (HTTP 404 unauthenticated) |
| openrouter |  | **NETWORK_BLOCKED** | — | — | — | egress proxy denied CONNECT to openrouter.ai (403 Forbidden) |
| cloudflare |  | **NETWORK_BLOCKED** | — | — | — | egress proxy denied CONNECT to api.cloudflare.com (403 Forbidden) |
| huggingface |  | **NETWORK_BLOCKED** | — | — | — | egress proxy denied CONNECT to router.huggingface.co (403 Forbidden) |
| ollama |  | **LIVE_FAILED** | — | — | — | http://localhost:11434: network: ConnectError: [Errno 111] Connection refused |
| llamacpp |  | **LIVE_FAILED** | — | — | — | http://localhost:8080: network: ConnectError: [Errno 111] Connection refused |
| mlx |  | **LIVE_FAILED** | — | — | — | http://localhost:8081: MLX requires Apple Silicon (macOS arm64) |
| vllm |  | **CREDENTIALS_REQUIRED** | — | — | — | no endpoint configured (VLLM_BASE_URL) |
| sglang |  | **CREDENTIALS_REQUIRED** | — | — | — | no endpoint configured (SGLANG_BASE_URL) |
| llamacpp_local | gpt-oss-20b-mxfp4 | **UNKNOWN** | — | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | nemotron-3-nano-4b-q4km | **UNKNOWN** | — | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | qwen3-vl-4b-q4kxl | **UNKNOWN** | — | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | gemma-multimodal | **LIVE_TESTED** | True | 4.6 s | 2026-10-10 16:23 | {"deadline": "2027-01-15", "fee_usd": 65} · local llama-server process on 127.0.0.1 — no billing surface |

**Totals:** CREDENTIALS_REQUIRED 3, LIVE_FAILED 3, LIVE_TESTED 1, NETWORK_BLOCKED 5, UNKNOWN 3

## What this means (derived from the rows above)

* **CREDENTIALS_REQUIRED**: gemini, sglang, vllm
* **LIVE_FAILED**: llamacpp, mlx, ollama
* **LIVE_TESTED**: llamacpp_local
* **NETWORK_BLOCKED**: cloudflare, groq, huggingface, nvidia_nim, openrouter
* **UNKNOWN**: llamacpp_local

* Executable $0 routes with a correct live structured answer: gemma-multimodal.
* NETWORK_BLOCKED rows are not routed around; CREDENTIALS_REQUIRED rows were not given accounts.
* Local models whose licence is not verified in the licence registry are used for EVALUATION only.

