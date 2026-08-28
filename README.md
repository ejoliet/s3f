# s3f

**fzf over a billion S3 objects — preview terabytes, download kilobytes.**

Interactive terminal browser for S3 at any scale. Streams object listings into fzf, previews files with byte-range GETs only (Parquet schema, FITS headers, image thumbnails rendered in-terminal), and shares any object to Slack in one keystroke.

> Type A RDD spec — an agent implements this end-to-end from this README. Resolve Open Questions first.

---

## Purpose

**Problem.** Exploring large S3 buckets is miserable. The AWS console paginates 300 objects at a time. `aws s3 ls` gives no search, no preview, no context. Answering "what's actually in this prefix, and what does the data look like?" means downloading files.

**Solution.** `s3f` pipes S3 listings into fzf's fuzzy interface. The preview pane never downloads whole objects — it issues HTTP range requests: Parquet footers for schema + row counts, FITS headers for astronomical metadata, image bytes for a chafa-rendered thumbnail. Enter posts a presigned URL + metadata card to Slack.

**Who benefits.** Data engineers, astronomers on public archives (IRSA, NASA, Sentinel-2, Common Crawl), any team fighting the S3 console.

**Headline stat the tool must self-report:** bytes browsed vs. bytes transferred (e.g., "Browsed 3.2 TB, downloaded 41 KB").

---

## Architecture

```
┌────────────┐   ListObjectsV2 (paginated, lazy)   ┌─────────┐
│ s3f list   │────────────────────────────────────▶│  fzf    │
│ (boto3)    │   one line per object (tab-sep)     │  UI     │
└────────────┘                                     └────┬────┘
                                                        │ --preview 's3f preview {}'
                                                   ┌────▼────────────┐
                                                   │ s3f preview     │
                                                   │ range GET only: │
                                                   │  .parquet→footer│
                                                   │  .fits→header   │
                                                   │  .jpg/.png/.tif │
                                                   │   →chafa render │
                                                   └────┬────────────┘
                                          Enter / ctrl-s│
                                                   ┌────▼────────────┐
                                                   │ s3f share       │
                                                   │ presign + Slack │
                                                   │ Block Kit card  │
                                                   └─────────────────┘
```

**Data flow.**
1. `s3f browse s3://bucket/prefix` spawns fzf with `--bind 'start:reload:s3f list ...'` — fzf handles millions of items, and `reload` bound to key/change events restarts the feeder process without restarting fzf, which is how prefix pivoting works.
2. Each fzf line: `key<TAB>size<TAB>last_modified<TAB>storage_class`. Bucket carried via env var, not per-line.
3. Preview pane shells back into the same binary (`s3f preview`), which dispatches on extension and issues ranged reads only.
4. `enter` → `become(s3f share {1})`; `ctrl-s` → share without exiting.
5. A byte-transfer counter persists per session in `$XDG_STATE_HOME/s3f/session.json` — the viral stat.

---

## Recommended Stack

| Layer | Chosen | Why | Rejected |
|-------|--------|-----|----------|
| S3 access | **boto3** | Already Emmanuel's stack; paginators, presigning, and `signature_version=UNSIGNED` for public Open Data buckets in one lib | `s5cmd` (fast but external binary, no presign card metadata); raw `aws s3api` (slow subprocess-per-page) |
| Parquet metadata | **pyarrow** (`ParquetFile` over `pyarrow.fs.S3FileSystem`) | Reads footer via range requests without full download; already in stack | `duckdb` httpfs (heavier dep for metadata-only); `fastparquet` (weaker S3 lazy-read story) |
| FITS header | **astropy.io.fits** with `use_fsspec=True` + `fsspec[s3]` | Ranged header reads on S3-hosted FITS; standard at IPAC | hand-rolled 2880-byte block reader (works — reuse astrohead logic as fallback if fsspec misbehaves) |
| Terminal images | **chafa** (external binary) | Best general-purpose choice per current comparisons: widest format support, ASCII-to-sixel output; auto-detects sixel/Kitty/iTerm protocols | viu (fewer formats), timg (video focus, unneeded) |
| Fuzzy UI | **fzf ≥ 0.44** | `reload`, `become`, `--preview`, `--listen`; no realistic alternative | skim (smaller ecosystem), textual TUI (weeks not a day) |
| Slack | **Incoming Webhook** (stdlib `urllib` POST) | 20 lines, no OAuth; Block Kit cards work over webhooks | `slack_sdk` (needed only for file uploads — out of scope v1) |
| CLI framework | **click** | Subcommands (`browse`/`list`/`preview`/`share`), env-var integration | argparse (fine but noisier), typer (extra dep over click for no gain here) |

> 💡 The no-dependency philosophy is explicitly waived for this project. Speed of build > purity. uv manages everything.

---

## Repository Layout

```
s3f/
├── README.md                 # this file
├── LICENSE                   # MIT
├── pyproject.toml            # uv-managed; console_script: s3f
├── src/s3f/
│   ├── __init__.py
│   ├── cli.py                # click entrypoint: browse, list, preview, share, stats
│   ├── listing.py            # boto3 paginator → line stream; anonymous-mode detection
│   ├── previews/
│   │   ├── __init__.py       # extension → handler dispatch
│   │   ├── parquet.py        # footer → schema, row count, size, compression
│   │   ├── fits.py           # primary HDU header → key cards table
│   │   ├── image.py          # ranged GET (cap 2 MB) → chafa subprocess
│   │   └── generic.py        # head bytes hexdump/text sniff for everything else
│   ├── share.py              # presign + Slack Block Kit webhook POST
│   ├── meter.py              # bytes-browsed vs bytes-transferred counter
│   └── fzf.py                # fzf invocation builder (binds, preview cmd, colors)
├── tests/                    # pytest + moto; no real AWS calls
└── .github/workflows/ci.yml  # ruff + mypy + pytest
```

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| fzf | ≥ 0.44 | `brew install fzf` / `apt install fzf` |
| chafa | ≥ 1.12 | `brew install chafa` / `apt install chafa` |
| AWS credentials | optional | Not needed for public buckets (anonymous mode) |
| Slack webhook URL | optional | Only for `share`; feature degrades gracefully without it |

---

## Quick Start

```bash
git clone git@github.com:ejoliet/s3f.git && cd s3f
uv sync
# Public bucket, zero credentials:
uv run s3f browse s3://nasa-irsa-spherex/ --anonymous
# Your own bucket:
uv run s3f browse s3://my-bucket/pipeline-outputs/
# End of session prints: "Browsed 3.2 TB across 1,204,551 objects. Transferred 41 KB."
```

Key bindings inside fzf:

| Key | Action |
|-----|--------|
| type | fuzzy filter loaded keys |
| `ctrl-r` | reload listing from current prefix filter `{q}` |
| `ctrl-p` | descend into selected "directory" prefix (reload) |
| `enter` | share to Slack and exit, printing presigned URL |
| `ctrl-s` | share to Slack, stay in fzf |
| `ctrl-y` | copy presigned URL to clipboard (pbcopy/xclip) |

---

## Configuration Reference

| Env var | Type | Default | Required | Purpose |
|---------|------|---------|----------|---------|
| `S3F_SLACK_WEBHOOK_URL` | str | — | no | Incoming webhook; `share` errors cleanly if unset |
| `S3F_SLACK_CHANNEL_LABEL` | str | — | no | Display-only channel name in card footer |
| `S3F_PRESIGN_TTL` | int (s) | `3600` | no | Presigned URL lifetime |
| `S3F_PREVIEW_MAX_BYTES` | int | `2097152` | no | Hard cap per preview range GET (2 MB) |
| `S3F_LIST_PAGE_SIZE` | int | `1000` | no | ListObjectsV2 page size |
| `S3F_LIST_MAX_KEYS` | int | `2000000` | no | Safety cap on streamed keys per reload |
| `S3F_ANONYMOUS` | bool | `false` | no | Force unsigned requests (public buckets) |
| `AWS_PROFILE` / standard AWS vars | — | — | no | Normal boto3 credential chain |

Secrets: webhook URL lives in `.env` (gitignored) or shell profile — never committed. `.env.example` ships with placeholders.

---

## Interface Contract

```
s3f browse S3URI [--anonymous] [--filter GLOB]     # main entry; spawns fzf
s3f list   S3URI [--anonymous]                     # line stream (fzf feeder; also useful standalone)
s3f preview KEY                                    # bucket via S3F_BUCKET env; writes preview to stdout
s3f share  KEY [--ttl SECONDS] [--no-slack]        # presign; post Block Kit card; print URL
s3f stats                                          # print session byte meter
```

**Preview output contract (per type):**
- Parquet: schema (column: type), `num_rows`, `num_row_groups`, file size, compression codec, created-by. Bytes fetched: footer only (typically 8–64 KB).
- FITS: primary header cards filtered to a curated set (`TELESCOP INSTRUME DATE-OBS RA_TARG DEC_TARG NAXIS*`) + full card count. Bytes fetched: first N×2880-byte blocks.
- Images (`.jpg .jpeg .png .tif .tiff .gif`): ranged GET up to `S3F_PREVIEW_MAX_BYTES`, piped to `chafa --size {cols}x{rows} -f auto`. If chafa absent → text metadata fallback, never crash.
- Everything else: first 4 KB; UTF-8 text shown as-is, binary shown as `xxd`-style hexdump.
- Every preview footer line: `↓ fetched 23.4 KB of 1.2 GB object`.

**Slack Block Kit card:** header (key basename), fields (bucket, size, last modified, type-specific facts like row count or `TELESCOP`), image block with presigned URL for image types, button-style link "Open (presigned, 1h)".

---

## Error Handling

| Error class | Trigger | Behavior |
|-------------|---------|----------|
| `S3fAccessDenied` | 403 on list/get | Suggest `--anonymous` toggle or profile; exit 3 |
| `S3fNoSuchBucket` | 404 bucket | Clear message; exit 4 |
| `S3fPreviewError` | corrupt footer/header, oversized range | Caught inside preview — render error *in the pane*, never kill fzf |
| `S3fSlackError` | webhook non-200 | Print body; still print presigned URL (share never loses the URL); exit 5 |
| Throttling (`SlowDown`) | S3 503 | botocore adaptive retry mode, max 5 attempts |

Rule: `s3f preview` must **never** exit non-zero in a way that blanks the fzf pane — trap everything, print the problem.

---

## Testing

- `pytest` + `moto[s3]` for listing, presigning, meter. No real AWS calls in CI.
- Fixture files: 1 tiny Parquet (pyarrow-generated in-test), 1 minimal FITS (astropy-generated), 1 PNG.
- Slack: `responses`/httpretty stub of webhook; assert Block Kit JSON shape.
- Preview handlers tested against moto-hosted fixtures, asserting **bytes fetched < file size** (the core invariant — meter makes this assertable).
- `make test` = `uv run pytest`; `make lint` = `ruff check && mypy --strict src/`.

---

## Agent Build Instructions

> Implement end-to-end using only this README. Resolve Open Questions first. Use `AIDEV-NOTE:` comments for non-obvious decisions.

### Build Order

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| 0 | Scaffold: pyproject (uv), ruff/mypy config, CI, MIT license | `make lint` passes on empty modules |
| 1 | `listing.py` + `meter.py` + anonymous mode | moto tests pass; `s3f list` streams a public bucket |
| 2 | `previews/` all four handlers | fixture tests pass; byte-cap invariant asserted |
| 3 | `fzf.py` + `cli.py browse` wiring | manual: browse a public bucket, previews render, `ctrl-r` reloads |
| 4 | `share.py` Slack card + presign + `ctrl-y` clipboard | stubbed webhook test passes; manual card posts |
| 5 | Session stats + polish (colors, `--help`, README demo GIF) | end-to-end demo recorded |

### Constraints

- Python 3.11+, typed signatures everywhere; `ruff` + `mypy --strict` clean.
- Preview latency budget: < 800 ms p50 on a warm connection — parallelize nothing yet; just keep range GETs small.
- No secrets in code or committed files; webhook via env only.
- Listing must stream (yield per page) — never accumulate all keys in Python memory; fzf holds the list.
- Every S3 byte fetched flows through `meter.py` (single choke point: a wrapped botocore session or explicit `record(n)` calls at all GET sites).

### Acceptance Criteria

- [ ] `make test` passes, coverage ≥ 80%; `make lint` passes
- [ ] `s3f browse s3://<public-bucket>/ --anonymous` works with zero AWS config
- [ ] Parquet/FITS/image/generic previews all render; corrupt file shows error in pane, fzf survives
- [ ] Bytes-transferred counter provably < 0.01% of bytes browsed in the demo run
- [ ] Slack card renders with image thumbnail for an image object
- [ ] Demo GIF: satellite image thumbnail inside the fzf preview pane

---

## Non-Goals (v1)

- Uploads, deletes, or any write operation against S3
- Cross-bucket or cross-account search; one bucket per session
- Full-object download command (users have `aws s3 cp`)
- Slack file uploads (webhook cards only; presigned image URLs suffice)
- GCS/Azure backends
- Windows support

---

## Open Questions

1. **Demo bucket for launch post** — Sentinel-2 (`s3://sentinel-s2-l2a` is requester-pays — verify), NOAA GOES, or an IRSA public bucket? Requester-pays changes the anonymous story; pick a truly free one.
2. **Terminal target for the GIF** — chafa auto-negotiates, but sixel quality varies; record demo in a sixel- or Kitty-protocol-capable terminal for maximum wow.
3. **Prefix navigation model** — treat `/`-delimited prefixes as a fake filesystem (`Delimiter='/'`, two-level UX) or flat-list everything and rely on fuzzy filter? Recommendation: flat by default, `--delimited` flag for huge buckets.
4. **Name collision check** — search GitHub/PyPI for existing `s3f` before publishing; fallback names: `s3fz`, `fz3`.

---

## Next Steps

1. Resolve Open Questions 1 and 4 (10 min).
2. Spike Phase 2's image path standalone first: ranged GET → chafa in an fzf preview pane. This is the only technical risk; if it works, everything else is assembly.
3. Hand this README to an agent for Phases 0–5.
4. Before publishing the repo or launch post: run `ship-check`.
