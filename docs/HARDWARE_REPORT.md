# JARVIS Hardware Report

Audit date: 2026-08-19  
Hosted-model strategy verified: 2026-08-20
Method: lightweight Windows CIM/PnP queries, installed-command checks, Phase 1/2 benchmarks, and
Phase 3 read-only capability probes plus disposable controlled-root benchmark

## Phase 1–4 revalidation update — 2026-08-31

- Phase 1 deterministic: 20/20, p50/p95 6.204/6.691 ms.
- Local `nemotron-3-nano:4b`: 20 verified-cold and 20 warm successes. Cold p50/p95
  9,477.214/10,927.172 ms; warm p50/p95 2,344.215/4,078.548 ms. Both miss the fixed
  1,500/3,000 ms targets. Installed artifact: 2,837,597,147 bytes, 3,973,556,832 parameters,
  Q4_K_M, SHA-256 digest `6cc467f054393a55e98a74098abde0c762ffb6d1d8cd64becf30458f38886197`;
  active context 4,096.
- The configured zero-cost NVIDIA model still passes catalog validation, but current public-fixture
  production requests timed out and fell back locally. No successful hosted sample or quota-ceiling
  probe was recorded; the 2026-08-22 live response is historical, not current availability proof.
- Fresh Phase 2 CPU STT with the local LLM resident: 30/30, short p50/p95 474.71/501.76 ms,
  RTF p95 0.2812, quiet/noisy WER 0%, accented WER 17.25%, and zero errors. Fresh trigger suite:
  wake/clap 20/20 each and zero false accepts in one simulated hour. Fresh 1,800.05-second soak:
  19,501 frames, 1,800 turns, zero failures, 152,723,456-byte peak RSS growth, final idle.
- Fresh Phase 3 safe benchmark: 700 authority checks p50/p95 0.130/0.215 ms; 250 fake dispatches
  0.220/0.244 ms; 24 real disposable move/rollback rounds 51.140/58.676 ms; zero false accepts,
  duplicates, unauthorized effects, failures, or remnants. No current app/audio/media effect ran.
- Fresh Phase 4 memory benchmark: warm 500-query p50/p95 1.2383/37.0088 ms; cold 20-query
  p50/p95 41.0982/80.0949 ms; 2,500 records at 2,157.7728 bytes/record; 100 concurrent operations
  with zero failures; deletion completeness 1.0.
- Current live microphone/render/kill and app/volume/media repetitions require separate authority.
  Existing 2026-08-22/26 live results remain historical evidence only.

## Phase 1 Nemotron acceptance update — 2026-08-22

- Installed Ollama `nemotron-3-nano:4b`: about 2.8 GB, Q4_K_M, tools and thinking.
- NVIDIA hosted `nvidia/nemotron-3-ultra-550b-a55b` catalog and live response passed.
- Three end-to-end simple local runs: 11.84, 3.49, and 2.93 seconds; warm average 3.21 seconds.
- Three forced hosted simple runs: 11.02, 3.17, and 2.20 seconds; warm average 2.69 seconds.
- These are smoke timings, not the 20+ sample p50/p95 closeout benchmark.

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
| System | ASUSTeK ASUS TUF Gaming F15 `FX506HF_FX506HF` |
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
| Project Python | `uv 0.12.5` provisions locked Python `3.11.16` |
| Node.js | Not found on `PATH` |
| Docker | Not found on `PATH` |
| WSL | `wsl.exe` present, but Windows reports WSL is not installed/configured |
| Ollama | Client/service `0.32.14`; local `nemotron-3-nano:4b` verified reachable in Phase 2 |
| CUDA toolkit | `nvcc` not found; full developer toolkit not installed/on `PATH` |
| NVIDIA driver CUDA support | Present through display driver; this is distinct from the CUDA toolkit |
| Vulkan tooling | Present |

DirectML capability was not separately benchmarked. Both detected display adapters are normal Windows graphics devices, but actual DirectML operator/performance support must be validated with the chosen runtime. Do not install CUDA, Docker, Node, or WSL until an implementation phase requires them.

System Python 3.14 does not satisfy the repository constraint `>=3.11,<3.13`; the locked `uv`
environment now correctly isolates Python 3.11.16. Continue avoiding global packages.

## Audio and camera

PnP reports these relevant devices as healthy:

- Microphone Array (Realtek Audio)
- Speakers (Realtek Audio)
- ASUS AI noise-cancelling input/output endpoints
- Bluetooth Crusher ANC 2 headset/headphones endpoints
- USB2.0 HD UVC WebCam

Steam streaming and monitor/display-audio endpoints also exist. Voice setup must persist explicit capture/render device IDs rather than rely on whichever Windows endpoint is default. Bluetooth hands-free mode may reduce audio quality and must be benchmarked separately from stereo output plus laptop microphone.

The matching ASUS FX506H-series manual documents **Fn+F4** as microphone on/off. This provides a
host-controlled physical hotkey independent of JARVIS; the software kill path remains
`jarvis voice disable`.

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

- Current local default: `nemotron-3-nano:4b`; start with bounded 4K/8K working context.
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
| `REASONING` | NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` | 1,000,000-token context; 32,768-token maximum output; text, tools, and thinking | Trial capacity uses model/account-specific unpublished limits |
| `LOCAL` | Ollama `nemotron-3-nano:4b` | 256K advertised model context; use bounded 4K/8K working context on this laptop | Hardware-limited but private/offline |

NVIDIA trial capacity is model/account-specific and visible in the API Catalog UI rather than a fixed published RPM. Free service is not an SLA. Quota exhaustion falls back locally or returns a capacity error. NVIDIA trial APIs receive public content only.

Sources: [NVIDIA Nemotron 3 Ultra](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard), [NVIDIA API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b), and [NVIDIA trial terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf).

## Voice and multimodal implications

The 4 GB GPU cannot be assumed to hold the main 4B LLM and a useful Whisper model concurrently.
Phase 2 therefore selected CPU speech after comparing the available resource strategies:

1. CPU faster-whisper small/int8 plus GPU-resident LLM;
2. GPU STT with explicit model unload/swap;
3. a smaller local command LLM during voice sessions;
4. optional cloud STT only when privacy policy permits.

The implemented profile keeps Silero VAD, faster-whisper, openWakeWord, and Windows SAPI TTS on
CPU. The discrete GPU remains available to Ollama. Cloud speech is not configured. Use the
integrated GPU for display where possible; future vision fast paths should use MediaPipe/OpenCV and
bounded frame rates, with multimodal LLM calls on demand rather than continuously.

### Phase 2 measured voice results — 2026-08-22

| Measurement | Result |
| --- | --- |
| Speech profile | 16 kHz mono, Silero VAD 6.2.1, faster-whisper 1.2.1 `base.en`, CPU/int8, 4 threads |
| STT cold load | 2,996.07 ms; CLI warms models before showing `MIC ON` |
| Short interactive STT | p50 530.71 ms; p95 694.78 ms; RTF p95 0.3101 |
| WER | quiet 0%; deterministic 10 dB SNR noisy 0%; 10 public real-accent samples 17.25% |
| Voice process memory | 55.48 MiB start; 513.76 MiB peak; 458.28 MiB growth |
| Loaded local LLM GPU state | 2,249 MiB before CPU speech; 2,251 MiB after; +2 MiB, 52 C final snapshot |
| Barge/output stop | 30 samples; p50 9.41 ms; p95 22.75 ms |
| Actual devices | Realtek mic 992 ms/zero drops; silent SAPI-format 22.05 kHz mono render completed on Crusher ANC 2 |
| Software kill during actual capture | Cancelled and persisted disabled in 594.52 ms |
| 30-minute real-time soak | 21,560 detector frames; 1,800 state turns; zero failures; 159.52 MiB peak growth; final idle |
| Model storage | STT cache 147,770,612 bytes; wake assets 9,195,168 bytes; outside Git |

The faster-whisper cache resolved revision `3d3d5dee26484f91867d81cb899cfcf72b96be6c`.
The long accent passages are 22–44 seconds and have p95 batch latency 6,058.90 ms but p95 RTF
0.1755; they are used for WER, not the short-interactive latency gate. All declared Phase 2
resource/latency thresholds passed with the local 4B model loaded.

### Phase 3 controlled-action results — 2026-08-22

The final pre-live Phase 3 benchmark ran as the current non-elevated Windows user. Evidence is in
`runtime/phase3-benchmark-20260822-a5/phase3-benchmark.json`. It used fake authority/broker adapters
plus 24 real same-volume handle-bound rename/rollback round trips inside a new disposable `runtime/`
controlled root. It sent no keyboard/media input, changed no volume or clipboard, launched no
application, and submitted no print job.

| Measurement | Result |
| --- | --- |
| Exact permission/grant validation | 700 samples; p50 0.135 ms; p95 0.234 ms; 0 false accepts |
| Invalid categories | Expired, replay, cross-session, wrong-host, mutated, wrong-action: 0 accepted |
| Fake broker dispatch | 250 samples; p50 0.226 ms; p95 0.278 ms; 0 duplicate effects |
| Reversible file move | 24 round trips; p50 54.984 ms; p95 60.343 ms |
| File postcondition/recovery | 24/24 verified moves; 24/24 guarded rollbacks; 0 destination remnants |
| Escape/unauthorized effects | Escape attempt refused; 0 unauthorized effects/failures |
| Core Audio read-only probe | Default console render endpoint scalar/mute query succeeded |
| Printer read-only probe | 2 installed local queues; 2/2 status queries succeeded; no job sent |

The target Windows build exposes Core Audio endpoint volume, `SendInput`, local print spooler,
clipboard, process-image query, file-ID/path, and rename primitives required by the fixed adapters.
The separately authorized live acceptance run on 2026-08-26 passed through the production trusted
CLI, coordinator, and broker. Evidence is in
`runtime/phase3-live-smoke-20260826-01/result.json`.

| Live action | Result |
| --- | --- |
| Enrolled disposable app fixture | Succeeded in 36.942 ms; exact image verified; exited after 2.001 seconds |
| Near-no-op master-volume write | Succeeded in 23.551 ms; target/readback 38%; scalar delta 0.0; mute unchanged |
| Global media STOP | Succeeded in 16.636 ms; exactly one key-down/key-up pair accepted; playback state not observable |

The run read/wrote no clipboard data, submitted no print job, accessed no user file, and used no
network. Clipboard writes and physical printing remain real host-visible effects requiring their
own separate authorization; they were not needed for Phase 3 acceptance.

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
  + Ollama Nemotron 3 Nano 4B LOCAL for normal/private/offline work
  + NVIDIA Nemotron 3 Ultra REASONING for safe difficult public work
  + optional Groq/Gemini adapters remain configuration-driven
  + hard zero-dollar cloud budget
  + CPU-first speech components
```

This profile should produce a responsive MVP while preserving a clean migration path to a 16–24+ GB VRAM server.
