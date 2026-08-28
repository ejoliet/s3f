# s3f implementation notes

## Unknowns audit
- Known knowns: full spec in README.md (interface contract, error table, build order).
- Known unknowns: OQ1 demo bucket (defer, launch-only); OQ2 GIF terminal (defer, launch-only); OQ3 prefix nav (resolved: flat default + --delimited per README rec); OQ4 name (resolved below).
- Unknown knowns surfaced: meter must see EVERY GET byte -> pyarrow.fs.S3FileSystem / astropy fsspec would bypass meter; use boto3-backed file-like reader instead.
- Unknown unknowns watched: aiobotocore/fsspec version hell (avoided by not depending on them); chafa absent on dev machine (fallback path is spec'd).

## Decisions
- 2026-08-27 OQ4: PyPI `s3f` taken (HTTP 200), `s3fz` free (404). CLI/repo stay `s3f`; publish under `s3fz` if/when published.
- 2026-08-27 OQ3: flat listing default, `--delimited` flag for Delimiter='/' mode, per README recommendation.
- 2026-08-27 DEVIATION: parquet/fits previews fetch bytes via own boto3 ranged file-like (previews/__init__.py) instead of pyarrow.fs.S3FileSystem / astropy use_fsspec. Why: README constraint "every S3 byte fetched flows through meter.py" is impossible if pyarrow C++/aiobotocore fetch directly; also drops fsspec+aiobotocore deps. astropy still parses headers (Header.fromstring), pyarrow still parses footers (ParquetFile over file-like). README itself blesses hand-rolled FITS fallback.
- 2026-08-27 Session model: single $XDG_STATE_HOME/s3f/session.json; `browse` resets it at start; preview/share subprocesses spawned by fzf increment it (read-modify-write, best effort).
- 2026-08-27 chafa not installed on dev machine; image preview tested via metadata fallback path per spec ("if chafa absent -> text metadata fallback, never crash").
- 2026-08-27 DEVIATION: README testing section says `responses` stubs the webhook, but `responses` only patches `requests`; share.py uses stdlib urllib per the chosen stack, so tests stub `s3f.share.urlopen` via monkeypatch (conftest `slack` fixture).
- 2026-08-27 Live verification (anonymous, zero AWS config): listed s3://nasa-irsa-spherex/qr2/abs_gain_matrix/, previewed a 15.9 MB FITS fetching 2.8 KB (header blocks only); session meter: "Browsed 95.3 MB across 6 objects. Transferred 2.8 KB" (0.003% << 0.01% acceptance bar).
- 2026-08-27 Left out: demo GIF (needs interactive terminal recording + chafa install) and live chafa thumbnail test (chafa absent on this machine; fallback path unit-tested).
