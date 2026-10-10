# Live Provider Report (Phase 14)

_Generated 2026-10-10 16:29 UTC by `apex-one reports build` from measured artifacts._

Statuses: LIVE_TESTED (a real structured task ran through the $0 firewall and returned output), LIVE_FAILED, CREDENTIALS_REQUIRED, NO_FREE_ROUTE, NETWORK_BLOCKED (egress proxy denied CONNECT), LICENSE_BLOCKED, UNKNOWN. A status is never inferred: rows without an executed call are not LIVE_TESTED.

| provider | model | status | structured task correct | latency | evidence |
|---|---|---|---|---|---|
| nvidia_nim |  | **NETWORK_BLOCKED** | — | — | egress proxy denied CONNECT to integrate.api.nvidia.com (403 Forbidden) |
| groq |  | **NETWORK_BLOCKED** | — | — | egress proxy denied CONNECT to api.groq.com (403 Forbidden) |
| gemini |  | **CREDENTIALS_REQUIRED** | — | — | reachable (HTTP 404 unauthenticated) |
| openrouter |  | **NETWORK_BLOCKED** | — | — | egress proxy denied CONNECT to openrouter.ai (403 Forbidden) |
| cloudflare |  | **NETWORK_BLOCKED** | — | — | egress proxy denied CONNECT to api.cloudflare.com (403 Forbidden) |
| huggingface |  | **NETWORK_BLOCKED** | — | — | egress proxy denied CONNECT to router.huggingface.co (403 Forbidden) |
| ollama |  | **LIVE_FAILED** | — | — | http://localhost:11434: network: ConnectError: [Errno 111] Connection refused |
| llamacpp |  | **LIVE_FAILED** | — | — | http://localhost:8080: network: ConnectError: [Errno 111] Connection refused |
| mlx |  | **LIVE_FAILED** | — | — | http://localhost:8081: MLX requires Apple Silicon (macOS arm64) |
| vllm |  | **CREDENTIALS_REQUIRED** | — | — | no endpoint configured (VLLM_BASE_URL) |
| sglang |  | **CREDENTIALS_REQUIRED** | — | — | no endpoint configured (SGLANG_BASE_URL) |
| llamacpp_local | gpt-oss-20b-mxfp4 | **UNKNOWN** | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | nemotron-3-nano-4b-q4km | **UNKNOWN** | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | qwen3-vl-4b-q4kxl | **UNKNOWN** | — | — | acquired but server not running (apex-one local serve) |
| llamacpp_local | gemma-multimodal | **LIVE_TESTED** | True | 4.6 s | {"deadline": "2027-01-15", "fee_usd": 65} · local llama-server process on 127.0.0.1 — no billing surface |

**Totals:** CREDENTIALS_REQUIRED 3, LIVE_FAILED 3, LIVE_TESTED 1, NETWORK_BLOCKED 5, UNKNOWN 3

## What this means

* Every cloud free tier (NVIDIA NIM, Groq, OpenRouter, Cloudflare Workers AI, Hugging Face) is NETWORK_BLOCKED from this container: the egress proxy refuses CONNECT. They are not routed around.
* Gemini is reachable but has no key in this environment (CREDENTIALS_REQUIRED). No account was created.
* The only executable $0 routes are local llama.cpp servers running open-weight GGUF models acquired with sha256 verification. Their licences are UNKNOWN in the licence registry until a human records a verification, so they are used for EVALUATION (judging, benchmarking) and never write shipped content.

