# JARVIS Hardware Report

Audit date: 2026-08-19  
Hosted-model strategy verified: 2026-08-20
Method: lightweight Windows CIM/PnP queries, installed-command checks, and Phase 1 local smoke benchmark

## Phase 1 local acceptance update — 2026-08-20

- Installed and SHA-256-verified Ollama `qwen2.5:3b` artifact: about 1.9 GB.
- `jarvis doctor`: configuration, data directory, SQLite migrations, Ollama service,
  and configured local model all passed.
- Deterministic clock turn: about 1.1 seconds wall time, including CLI startup.
- First private local-model turn after load/install: about 50 seconds wall time; cold-load
  exception exceeds target and must remain visible.
- Five immediately warm private local turns, including CLI startup: 1.455, 1.181, 0.885,
  0.878, and 0.936 seconds. Observed p50 was 0.936 seconds and nearest-rank p95 was
  1.455 seconds.
- These five warm samples validate basic interactivity, not production statistical confidence.
  Re-run longer benchmarks after model, prompt, driver, or hardware changes.

## Summary

This laptop is suitable for JARVIS development, private/offline small-model fallback, local speech, and light vision. It is not suitable for a high-quality large local reasoning model. The target strategy is privacy-aware hybrid: deterministic privacy/command handling locally, free-tier hosted inference for non-sensitive work, and Ollama for sensitive content or cloud failure. Initial cloud spend is hard-capped at `$0`.

## Hardware discovered

| Area | Result |
| --- | --- |
| CPU | 11th Gen Intel Core i5-11400H @ 2.70 GHz |
| CPU topology | 6 physical cores / 12 logical processors |
| Installed memory | 16,888,967,168 bytes: 15.73 GiB (marketed 16 GB) |
| Available memory at audit | 6,525,220 KiB: about 6.22 GiB; volatile snapshot |
| Discrete GPU | NVIDIA GeForce RTX 2050 Laptop GPU |
| Dedicated VRAM | 4,096 MiB |
| NVIDIA compute | CUDA compute capability 8.6; driver 610.62 exposes CUDA UMD 13.3 |
| Integrated GPU | Intel UHD Graphics; shared-memory display adapter |
| Vulkan | `vulkaninfo.exe` present |
| Storage | `C:` NTFS, 484,602,875,904 bytes total (451.32 GiB) |
| Storage available | 377,488,711,680 bytes (351.56 GiB) at audit |
| OS | Microsoft Windows 11 Home, 64-bit |
| OS version | 10.0.26200, build 26200 |

The NVIDIA GPU was idle during inspection: 0 MiB reported in use, 41 °C, 0% utilization. These are observations, not thermal or sustained-performance results.

## Development environment

| Tool | State |
| --- | --- |
| Git | Installed, `2.55.0.windows.4` |
| Python | System Python `3.14.7` installed |
| Project Python | Project requests 3.11; `uv` is expected to provision it, but `uv` is not currently on `PATH` |
| Node.js | Not found on `PATH` |
| Docker | Not found on `PATH` |
| WSL | `wsl.exe` present, but Windows reports WSL is not installed/configured |
| Ollama | Client installed, `0.32.14`; service was not running/reachable during audit |
| CUDA toolkit | `nvcc` not found; full developer toolkit not installed/on `PATH` |
| NVIDIA driver CUDA support | Present through display driver; this is distinct from the CUDA toolkit |
| Vulkan tooling | Present |

DirectML capability was not separately benchmarked. Both detected display adapters are normal Windows graphics devices, but actual DirectML operator/performance support must be validated with the chosen runtime. Do not install CUDA, Docker, Node, or WSL until an implementation phase requires them.

Python 3.14 does not satisfy the repository constraint `>=3.11,<3.13`. This is not a reason to change the project constraint: install `uv`, let the locked project provision Python 3.11, and avoid global packages.

## Audio and camera

PnP reports these relevant devices as healthy:

- Microphone Array (Realtek Audio)
- Speakers (Realtek Audio)
- ASUS AI noise-cancelling input/output endpoints
- Bluetooth Crusher ANC 2 headset/headphones endpoints
- USB2.0 HD UVC WebCam

Steam streaming and monitor/display-audio endpoints also exist. Voice setup must persist explicit capture/render device IDs rather than rely on whichever Windows endpoint is default. Bluetooth hands-free mode may reduce audio quality and must be benchmarked separately from stereo output plus laptop microphone.

## Local model fit

VRAM is the primary constraint. Model file size is not total runtime memory: context KV cache, compute buffers, vision projector, runtime overhead, Windows WDDM, and concurrent STT/vision all add memory.

| Model class | Expected fit | Recommended use |
| --- | --- | --- |
| 0.5B–2B, 4-bit | Comfortable in VRAM with modest context | Intent, classification, short commands, fallback chat |
| 3B–4.7B, 4-bit | Borderline but plausible with modest context and careful offload | Main local text model; benchmark 4K/8K context first |
| 7B–9B, 4-bit | Exceeds 4 GB VRAM; partial CPU offload and 16 GB RAM make it slower | Evaluation only, not latency default |
| 14B, 4-bit | RAM pressure and poor laptop latency | Not recommended for daily local use |
| 30B+ | Impractical on this laptop | Dedicated server or cloud only |

Local fallback candidates, without downloading during planning:

- Compatibility default: retain the implemented `qwen2.5:3b` until benchmarks justify migration.
- Fast local candidate: `qwen3:1.7b` Q4 through Ollama; official Ollama artifact is about 1.4 GB.
- Main local candidate: `qwen3.5:4b` Q4_K_M; official Ollama artifact is about 3.4 GB. Limit context initially and measure VRAM headroom.
- Alternative main: `gemma3:4b`, about 3.3 GB, for an independent quality/license/tool-use comparison.
- Embeddings later: a sub-1B embedding model such as `qwen3-embedding:0.6b`, loaded on demand or CPU-resident.
- Heavy local reasoning: defer to a future server-hosted 14B–32B class.

Do not run advertised 128K/256K context merely because a model supports it. On this hardware, start at 4K and 8K; retrieval and summarization are cheaper and more predictable.

## Hosted model roles

Hosted catalog facts were verified from official provider documentation on 2026-08-20. They are dated observations, not local benchmark results or availability guarantees.

| Role | Provider/model | Verified catalog capability | Lifecycle risk |
| --- | --- | --- | --- |
| `FAST` | Groq `openai/gpt-oss-20b` | About 1,000 tokens/s; 131,072-token context; tools, reasoning, JSON object/schema modes | Production model; free tier remains quota-limited |
| `PRIMARY` | Groq `qwen/qwen3.6-27b` | About 500 tokens/s; 131,072-token context; text/images, tools, parallel calls, vision, thinking/non-thinking | Preview; startup catalog checks and fallback required |
| `REASONING` | Google `gemini-3.7-flash` | 1,048,576-token input; text/image/video/audio/PDF, tools, structured output, adjustable reasoning | Stable; free quota varies by project |
| `LOCAL` | Ollama configured model | Depends on local artifact/runtime; currently `qwen2.5:3b` | Hardware-limited but private/offline |

Groq currently lists both selected models on its free plan, but rate limits and capacity can change. Gemini free limits must be read from the active AI Studio project. Free service is not an SLA. Use billing-disabled credentials; quota exhaustion falls back locally or returns a capacity error. Enable Groq Zero Data Retention. Never send sensitive or confidential content through unpaid Gemini because its terms permit product-improvement use and human review.

Sources: [Groq models](https://console.groq.com/docs/models), [Groq limits](https://console.groq.com/docs/rate-limits), [Groq data controls](https://console.groq.com/docs/your-data), [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), and [Gemini terms](https://ai.google.dev/gemini-api/terms).

## Voice and multimodal implications

The 4 GB GPU cannot be assumed to hold the main 4B LLM and a useful Whisper model concurrently. Phase 2 must compare:

1. CPU faster-whisper small/int8 plus GPU-resident LLM;
2. GPU STT with explicit model unload/swap;
3. a smaller local command LLM during voice sessions;
4. optional cloud STT only when privacy policy permits.

Keep Silero VAD, openWakeWord, and Piper TTS on CPU initially. Use the integrated GPU for display and preserve the discrete GPU for inference where possible. Vision fast paths should use MediaPipe/OpenCV and bounded frame rates; multimodal LLM calls are on-demand, not continuous.

## Benchmark gate for model adoption

Use a fixed JARVIS workload rather than generic leaderboard scores:

- 20 short intent/command cases;
- 20 tool-schema selection cases including refusal/ambiguity;
- 20 normal conversation/personality cases;
- 10 planning/coding/reasoning cases;
- long-context retrieval cases at 4K and 8K;
- cold and warm start;
- time to first token and tokens/second;
- peak RAM/VRAM, GPU offload, power and temperature;
- tool-call exact match, reasoning rubric, hallucination/refusal rate;
- concurrent voice pipeline impact and 30-minute stability.

Record p50/p95, model digest, quantization, runtime version, context/output settings, and whether the laptop is plugged in. A model becomes the default only after it meets latency and correctness gates without unsafe thermal or memory pressure.

## Capacity recommendations

- Keep at least 50 GiB free for environments, logs, temporary media, and several explicitly installed models; current free space is sufficient.
- Store model weights outside Git and runtime data outside the checkout.
- Cap model concurrency at one heavy local inference job initially.
- Apply hard context/output limits and unload idle models based on measurements.
- Use encrypted backups for memory/audit data; model files are reproducible and need not be backed up.

## Conclusion

Recommended laptop profile:

```text
local deterministic sensitivity and command gate
  + Groq GPT-OSS 20B FAST for safe simple work
  + Groq Qwen 3.6 27B PRIMARY for safe normal work
  + Gemini 3.7 Flash REASONING for safe difficult work
  + Ollama LOCAL for private/offline/fallback work
  + hard zero-dollar cloud budget
  + CPU-first speech components
```

This profile should produce a responsive MVP while preserving a clean migration path to a 16–24+ GB VRAM server.
