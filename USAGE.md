# DwarfStar (ds4) — Command Reference

Local cheat sheet for this machine: **Apple M5 Max, 128 GB RAM, Metal build**.

Model in use:
`~/AI/models/pyrodog_DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2/DeepSeek-V4.1-Flash-UNCENSORED-Q2-bootstrap.gguf`
(341 GiB / Q2). At 341 GiB against 128 GB of RAM this model **requires
`--ssd-streaming`** — it will not load resident.

Shorthand used below:

```sh
MODEL=~/AI/models/pyrodog_DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2/DeepSeek-V4.1-Flash-UNCENSORED-Q2-bootstrap.gguf
```

Run commands from `/Users/xtk/opt/ds4` (or pass `--chdir /Users/xtk/opt/ds4`)
so the Metal kernels resolve.

---

## Binaries

| Binary | Purpose |
| --- | --- |
| `./ds4` | Interactive CLI / one-shot prompts |
| `./ds4-server` | HTTP server (OpenAI, Responses, Anthropic, completions APIs) |
| `./ds4-agent` | Native coding agent, no HTTP server |
| `./ds4-bench` | Benchmarks |
| `./ds4-eval` | Evaluation harness |

Each takes `--help`. `ds4-server` also has topic pages:
`--help runtime`, `--help api`, `--help kv-cache`, `--help thinking`,
`--help steering`, `--help distributed`.

---

## Start the server

The working configuration for this box:

```sh
./ds4-server \
  -m "$MODEL" \
  --ssd-streaming \
  --ctx 32768 \
  --kv-disk-dir ~/.ds4/server-kv --kv-disk-space-mb 8192
```

Listens on `http://127.0.0.1:8000`. Startup is ~2 s — SSD streaming skips full
residency and warmup.

Run it detached with a log:

```sh
./ds4-server -m "$MODEL" --ssd-streaming --ctx 32768 \
  --kv-disk-dir ~/.ds4/server-kv --kv-disk-space-mb 8192 \
  > /tmp/ds4-server.log 2>&1 &
```

Stop it:

```sh
pkill -f ds4-server
```

### Useful server flags

| Flag | Effect |
| --- | --- |
| `--port N` | Bind port (default 8000) |
| `--host 0.0.0.0` | Listen on all interfaces (no auth — trusted networks only) |
| `-c, --ctx N` | Allocated context tokens |
| `-n, --tokens N` | Default max output when the client omits a limit |
| `--cors` | Browser CORS headers (not access control) |
| `--batched-session N` | N resident sessions, batched decode |
| `--trace FILE` | Log prompts, cache decisions, output, tool calls |
| `--power N` | GPU duty-cycle target, 1..100 |

> `--batched-session` note: under **Metal SSD streaming** V4.1 uses the *ordered
> fallback*, not native batching — you get concurrency and fair scheduling, not
> aggregate speedup. Context that fits once may not fit N times.

### SSD streaming tuning

| Flag | Effect |
| --- | --- |
| `--ssd-streaming` | Opt in to SSD-backed streaming instead of full residency |
| `--ssd-streaming-cache-experts 32GB` | Byte budget for the expert cache (a target, not a guarantee) |
| `--ssd-streaming-cache-experts 4000` | Plain number = dynamic expert *slots* |
| `--ssd-streaming-preload-experts N` | Upfront popularity preload (DeepSeek auto-seeds by default) |
| `--ssd-streaming-cold` | Skip the preload — for controlled measurements only |
| `--simulate-used-memory NGB` | Lock N GiB before load to fake a smaller machine |

Auto budget is the right starting point. What it chose here:

```
metal recommends 121.60 GiB working set
using 81% total for model + cached experts: 98.00 GiB
non-routed weights: 9.37 GiB        routed expert size: 9.49 MiB
effective 88.63 GiB = 7.12 GiB prefill headroom + 81.51 GiB dynamic cache (8793 experts)
planned total: 105.88 GiB
```

Shrink the cache to free room for more context or sessions. An *oversized*
cache can displace the non-routed weights that every token needs and slow
decoding — more cache helps only while the rest of the working set still fits.

---

## Calling the API

Model id is **`deepseek-v4.1-flash`** (`deepseek-v4-flash` / `deepseek-v4-pro`
are compatibility aliases; the GGUF passed at startup is what actually loads).

```sh
curl -s http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

| Endpoint | Style |
| --- | --- |
| `GET /v1/models` | Loaded model info |
| `POST /v1/chat/completions` | OpenAI chat |
| `POST /v1/responses` | Responses |
| `POST /v1/completions` | Text completion |
| `POST /v1/messages` | Anthropic messages |

Quick smoke test:

```sh
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4.1-flash",
       "messages":[{"role":"user","content":"Say hello in exactly five words."}],
       "max_tokens":64,"think":false}' | python3 -m json.tool
```

Streaming:

```sh
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"Explain Redis streams."}],"stream":true}'
```

### Thinking

DeepSeek has thinking **on by default**. Turn it off per request with
`"think": false`, a disabled thinking object, or a non-thinking alias.
`reasoning_effort=max` selects Think Max only with enough context; `xhigh` maps
to normal thinking, not Think Max.

Default sampling: temperature 1, top-p 1, min-p 0.05. Explicit request
parameters win over defaults.

---

## mycli

`mycli`'s configured `base_url` is already `http://127.0.0.1:8000/v1`, so only
the model needs overriding:

```sh
mycli -m deepseek-v4.1-flash                      # REPL
mycli -m deepseek-v4.1-flash -y "fix the tests"   # single-shot, auto-approve tools
mycli -m deepseek-v4.1-flash --no-thinking        # faster, no reasoning traces
mycli --show-config                               # inspect current config
```

Handy flags: `-t simple|medium|full` (tool tier), `--max-turns N`,
`-p code|redteam|blueteam|data` (persona), `-C DIR` (working directory).

**Port conflict:** mycli's default model `Qwen3.6-35B-A3B-8bit` is served by
oMLX on this same port 8000. Only one of them can hold it. To run both:

```sh
./ds4-server -m "$MODEL" --ssd-streaming --ctx 32768 --port 8001
mycli -m deepseek-v4.1-flash --base-url http://127.0.0.1:8001/v1
```

---

## Interactive CLI and agent

```sh
./ds4 -m "$MODEL" --ssd-streaming --ctx 32768 --nothink
./ds4 -m "$MODEL" --ssd-streaming -p "Explain Redis streams in one paragraph."
./ds4-agent -m "$MODEL" --ssd-streaming --ctx 32768
```

CLI: `/help`, `/read FILE`, `/ctx N`, `/quit`. Ctrl+C interrupts generation and
returns to the prompt.

Agent sessions (stored in `~/.ds4/kvcache`): `/save`, `/list`, `/switch <sha>`,
`/del <sha>`, `/strip <sha>`. `/hints on|off` toggles brief explanations of
programming choices, applied at the next conversation boundary.

---

## Where ds4 keeps things on disk

**Weights are never copied.** SSD streaming reads routed experts on demand
straight out of the original GGUF — there is no cache file, no spill directory,
no converted copy. The only model-data file the running server has open is:

```
~/AI/models/pyrodog_DeepSeek-V4.1-Flash-UNCENSORED-DwarfStar-Q2/DeepSeek-V4.1-Flash-UNCENSORED-Q2-bootstrap.gguf
```

held open on 4 descriptors: one `txt` (the mmap'd model map, 569 spans /
9.37 GiB of resident tensor spans) plus read-only fds for streamed experts and
for Engram, which uses a separate *uncached* fd and `pread`s rows directly —
never an mmap or a Metal model view. Engram tables stay on disk in **every**
mode, resident or streaming, so the GGUF must live on a fast local SSD.

Consequence: the "cache" in `--ssd-streaming-cache-experts` is **RAM**, not
disk. Deleting the GGUF or moving it mid-run kills the server.

| Path | Contents | Notes |
| --- | --- | --- |
| The GGUF itself | All weights, Engram tables | Read in place; never duplicated |
| `~/.ds4/server-kv/` | Server disk KV checkpoints (`<sha>.kv`) | Only with `--kv-disk-dir`; bounded by `--kv-disk-space-mb` |
| `~/.ds4/kvcache/` | `ds4-agent` saved sessions | `/save`, `/list`, `/switch` |
| `/tmp/ds4.lock` | Single-instance lock | Override with `DS4_LOCK_FILE` |
| `gguf/` in repo root | Where `./download_model.sh` puts downloads | Not used by this model |
| `$TMPDIR/.../com.apple.metal/` | OS Metal shader cache | Managed by macOS |

Saved sessions and `--trace` files may contain private information.

Check actual usage:

```sh
du -sh ~/.ds4/*
lsof -p $(pgrep -f 'ds4-server -m') | grep gguf
ps -o rss=,vsz= -p $(pgrep -f 'ds4-server -m')   # RSS ~91 GB, VSZ ~736 GB here
```

VSZ is large because the whole 341 GiB GGUF is mapped; RSS is what is actually
resident.

---

## Disk KV cache

Speeds up repeated and continued prompts.

```sh
./ds4-server -m "$MODEL" --ssd-streaming --ctx 32768 \
  --kv-disk-dir ~/.ds4/server-kv --kv-disk-space-mb 8192
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--kv-disk-space-mb N` | 4096 | Disk budget when enabled |
| `--kv-cache-min-tokens N` | 512 | Skip checkpoints shorter than N |
| `--kv-cache-cold-max-tokens N` | 30000 | Save cold first prompts up to N; 0 disables |
| `--kv-cache-continued-interval-tokens N` | 10000 | Save aligned continued frontiers; 0 disables |
| `--kv-cache-reject-different-quant` | off | Reject checkpoints from a different routed-expert quant |

`usage.prompt_tokens_details.cached_tokens` in a response shows what was reused.

---

## Troubleshooting

**"failed to open lock file" / refuses to start.** ds4 takes a global
single-instance lock at `/tmp/ds4.lock` — the model can map tens of GiB, so a
stale second run is treated as dangerous. Kill the other process, or set
`DS4_LOCK_FILE=/tmp/ds4-b.lock` for a deliberate second instance.

**Port 8000 busy.** oMLX likely has it. `lsof -nP -iTCP:8000 -sTCP:LISTEN`,
then use `--port 8001`.

**Server exits during load.** Check the log. On this model, omitting
`--ssd-streaming` is the usual cause.

**Generation is too slow.** Expected for a Q2 MoE streaming off SSD —
generation is more cache-miss sensitive than prefill. A multi-tool agent turn
measured ~1m47s here. Try a short generation before committing to a long task.
Disabling the memory guard is not a remedy for insufficient RAM.

**Memory pressure.** Lower `--ctx`, lower `--ssd-streaming-cache-experts`, or
drop `--batched-session`. More context and more sessions cost more memory.
