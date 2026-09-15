# DeepSeek V4.1 Flash Q2: SSD streaming vs. the resident Flash Q2 baseline

[Benchmarking](README.md) | [Performance](../docs/PERFORMANCE.md) | [SSD streaming](../docs/SSD_STREAMING.md)

Measured 2026-09-15 on an Apple M5 Max, 128 GB, Metal build.

Interactive charts for these runs: [`flash_v41_q2-comparsion.html`](flash_v41_q2-comparsion.html)
(self-contained; open it locally in a browser), also published at
https://claude.ai/artifact/5DhtQRrQyVqffbWQ4AbsP1

## Why this comparison exists

`speed-bench/m5_max.csv` records a **resident** baseline for **DeepSeek V4 Flash
0731 Q2** (`ds4f-q2`, 81 GiB, 43 layers, 256 experts, no Engram). It is easy to
read those ~790 t/s prefill numbers as "what an M5 Max does", and then to read a
much lower number from a streamed V4.1 run as a regression.

They are not the same workload. The CSV schema carries no model or mode column,
so a file named for the hardware alone does not say what was run. This note
records the V4.1 streaming numbers next to that baseline, with the differences
stated explicitly.

| | `m5_max.csv` baseline | This note |
| --- | --- | --- |
| Model | DeepSeek V4 Flash 0731 Q2 | DeepSeek V4.1 Flash Q2 |
| Layers x experts | 43 x 256 | 40 x 384 |
| Experts used per token | 6 | 6 |
| File size | 81 GiB | 341 GiB |
| Weight residency | Fully resident | SSD streaming |
| Engram tables | None | 188.8 GiB, disk-only |

Both use the same machine, the same `promessi_sposi.txt` corpus, and the same
`ds4-bench` harness.

## Headline

**Prefill throughput under SSD streaming is governed by how full the prefill
chunk is, not by streaming itself.**

| Prefill increment | Prefill t/s | vs. resident baseline |
| --- | ---: | ---: |
| 2048 tokens | 59 - 130 | 6 - 9x |
| 8192 tokens | 215 - 408 | 1.7 - 2.6x |

Steady generation is flat at **16 - 17.5 t/s** in both runs, roughly 2.2x the
baseline's 35 - 40 t/s. Measuring at small increments makes streaming look about
four times worse on prefill than it is in normal use.

## Runs

Data files in this directory:

| File | Configuration |
| --- | --- |
| `m5_max_v41_q2_stream_incr2k.csv` | V4.1 Q2, streaming, 2048-token increments |
| `m5_max_v41_q2_stream_incr8k.csv` | V4.1 Q2, streaming, 8192-token increments |
| `m5_max.csv` | V4 Flash Q2, resident (existing baseline) |

Each `_ts.svg` is produced by `plot_speed.py` from the CSV beside it.

```sh
# 2048-token increments
./ds4-bench -m "$MODEL" --ssd-streaming \
  --prompt-file speed-bench/promessi_sposi.txt \
  --ctx-start 2048 --ctx-max 8192 --step-incr 2048 --gen-tokens 64 \
  --csv speed-bench/m5_max_v41_q2_stream_incr2k.csv

# 8192-token increments
./ds4-bench -m "$MODEL" --ssd-streaming --prefill-chunk 8192 \
  --prompt-file speed-bench/promessi_sposi.txt \
  --ctx-start 8192 --ctx-max 32768 --step-incr 8192 --gen-tokens 64 \
  --csv speed-bench/m5_max_v41_q2_stream_incr8k.csv
```

## Results

Generation figures are `gen_steady_tps`, which excludes the first-token wait.

### V4.1 Q2, streaming, 2048-token increments

| ctx | Prefill t/s | Gen t/s | First token (ms) |
| ---: | ---: | ---: | ---: |
| 2048 | 129.88 | 17.27 | 904.98 |
| 4096 | 83.52 | 16.71 | 139.32 |
| 6144 | 76.37 | 16.90 | 140.07 |
| 8192 | 80.88 | 17.35 | 135.88 |

### V4.1 Q2, streaming, 8192-token increments

| ctx | Prefill t/s | Gen t/s | First token (ms) |
| ---: | ---: | ---: | ---: |
| 8192 | 407.63 | 15.83 | 904.76 |
| 16384 | 254.84 | 17.13 | 736.34 |
| 24576 | 245.05 | 16.88 | 892.05 |
| 32768 | 215.36 | 16.42 | 427.38 |

### Resident V4 Flash Q2 baseline, for reference

| ctx | Prefill t/s | Gen t/s |
| ---: | ---: | ---: |
| 2048 | 790.18 | 40.00 |
| 8192 | 683.85 | 37.63 |
| 16384 | 572.53 | 36.68 |
| 32768 | 557.04 | 34.90 |

## Why chunk fill decides prefill

V4.1 selects 6 of 384 routed experts per layer per token. Decode therefore
touches 240 expert tensors for one token. A prefill chunk takes the **union**
over every token in it, so a large chunk touches effectively all 384 per layer:
15,360 expert tensors, about 142 GiB, against an expert cache of roughly 81 GiB.

That sweep is close to fixed per chunk. Its cost barely depends on how many
tokens ride along, so the per-token cost falls as the chunk fills. Amortized
over 2048 tokens it dominates; over 8192 it is around four times cheaper per
token.

Two consequences:

- Benchmarks that measure small prefill increments understate streaming prefill.
  The 2048-token frontier increments here are close to worst case.
- Decode cannot benefit the same way. It reads ~2.22 GiB of experts to produce a
  single token, the worst possible amortization ratio, which is why generation
  sits at 16 - 17.5 t/s regardless of chunk size.

### The chunk is clamped

`--prefill-chunk` is honored but clamped to the prompt length
(`ds4_prefill_cap_for_prompt`, `ds4.c:14321`); with no flag, the non-PRO default
for prompts over 4096 tokens is 4096. Passing `--prefill-chunk 8192` while
measuring 2048-token increments changes nothing, which a control run confirmed:
it reproduced the 2048-increment numbers (59 - 127 t/s).

The startup line `memory detail: ... prefill_cap=N` reports the allocation
ceiling, which tracks `--ctx`. Observed: `ctx=8257 -> 4096`, `ctx=32833 -> 8192`.

### Large prefills evict decode's working set

First-token latency after an 8192-token prefill ran 427 - 905 ms, against
121 - 148 ms after a 2048-token one. The chunk sweep displaces exactly the hot
experts decode wants back. Steady-state generation is unaffected.

## Context competes with the expert cache

Allocated context reduces the expert-cache budget:

| Allocated ctx | Effective expert cache |
| ---: | --- |
| 8257 | 86.50 GiB (9332 experts) |
| 32833 | 81.51 GiB (8793 experts) |

The 8192-increment run won by 3 - 4x **despite** the smaller cache, so chunk
fill matters more than cache size here. Raising `--ctx` to obtain chunk headroom
is worthwhile; raising it beyond that trades cache for nothing.

## Settings these numbers suggest

```sh
./ds4-server -m "$MODEL" --ssd-streaming \
  --ctx 32768 \
  --prefill-chunk 8192 \
  --kv-disk-dir ~/.ds4/server-kv --kv-disk-space-mb 32768
```

| Setting | Reason |
| --- | --- |
| `--ctx 32768` | Below roughly 32K the allocation caps `prefill_cap` at 4096 |
| `--prefill-chunk 8192` | Explicit rather than relying on the 4096 default |
| Large `--kv-disk-space-mb` | Re-prefill is the expensive operation; a 32K snapshot is ~475 MB, so 4096 MB holds very few |
| Avoid `--batched-session` | V4.1 on Metal streaming uses the ordered fallback, and each session's context steals from the expert cache |
| Avoid `--ssd-streaming-cold` | Skips the popularity preload; first-token latency degrades sharply |

## Caveats

- Single runs, not medians. `docs/PERFORMANCE.md` asks for alternating repeats
  before treating a number as a speed result.
- The resident baseline is a different checkpoint, not the same model streamed.
  Active footprint per token is close (~1.94 GiB for V4 Flash Q2 against
  ~2.22 GiB for V4.1 Q2), so it is a reasonable proxy, but it is not a
  controlled residency comparison. V4.1 Q2 cannot be resident on 128 GB: its
  main weights alone are about 152 GiB.
- The V4.1 checkpoint measured here is a third-party Q2 conversion. It omits the
  speculative-decoding draft weights, so MTP/DSpark was unavailable; a
  checkpoint retaining them should generate faster.
- A live `ds4-server` independently logged 216 - 296 t/s prefill on a 10k-token
  prompt at `prefill_chunk=8192`, consistent with the 215 - 408 t/s here.

## Reproducing the resident baseline

`ds4f-q2` is 81 GiB and fits resident on a 128 GB machine:

```sh
./download_model.sh ds4f-q2
./ds4-bench --prompt-file speed-bench/promessi_sposi.txt \
  --ctx-start 2048 --ctx-max 32768 --step-incr 2048 --gen-tokens 128 \
  --csv speed-bench/m5_max_repro.csv
```

No `--ssd-streaming` flag. Landing near 790 t/s prefill and 39 t/s generation
confirms both the recorded baseline and the penalty figures above.
