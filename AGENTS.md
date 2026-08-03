# AGENTS.md

## Cursor Cloud specific instructions

EvoQuant is a Python crypto-market "world model" data platform: data-layer collectors ingest
market/derivatives/on-chain/macro data, a logic-layer DAG computes features/indicators, and a
FastAPI service (`api/app.py`) serves quality-tagged market context to AI consumers. Storage
defaults to embedded SQLite, so no external database is required for local dev.

Standard commands live in the `Makefile` (`make test|lint|typecheck|api|dev|modules`), `api/README.md`,
and `README.md`. The notes below are only the non-obvious caveats.

### Environment / dependencies
- The VM runs Python 3.12 (project targets 3.11 in CI, but it installs and runs fine on 3.12). Work
  inside the virtualenv at `.venv` (`source .venv/bin/activate`).
- Dependency install order matters: `requirements-dev.txt` pins `safety==3.2.14`, which requires
  `pydantic<2.10`, conflicting with the runtime pin `pydantic==2.10.6`. Install `requirements.txt`
  **last** so the runtime `pydantic 2.10.6` wins. `safety` (a security scanner, unused for
  lint/test/build/run) is left with a harmless resolver warning; ignore it.

### Databases
- `DB_BACKEND` defaults to `sqlite` in `config/settings.py`, even though `.env.example` sets
  `postgres`. For local dev do **not** copy `.env` to enable Postgres unless you actually start one;
  the SQLite files are auto-created under `database/` (3-way split: `exchange_data.db`,
  `market_data.db`, `analytics.db`; set `DB_SPLIT_ENABLED=0` for a single file, as CI does for tests).

### Running services (SQLite, no secrets needed)
- API only: `python -m api.app --port 8000` (Swagger at `/docs`, 550 routes). Endpoints read the DB
  live, so data collected after startup shows up without a restart.
- Full orchestration (collectors + logic pipeline + API as supervised subprocesses): `python main.py`.
- Populate data manually: `python -m data_layer.exchange_data.runner --mode once` (add
  `--mode bootstrap` for historical klines), then `python -m logic_layer.logic_pipeline.runner --mode once`.

### API usage gotchas
- Symbol path params use `BASE-QUOTE`, e.g. `/exchange/ticker/BTC-USDT` (not `BTC/USDT` or `BTCUSDT`).
- Many endpoints default to `exchange=binance`; pass `?exchange=okx` when Binance data is absent.

### Network / exchange caveats (important for data collection)
- From this VM, Binance returns HTTP 451 (geo-block) and Bybit returns HTTP 403; **only OKX is
  reachable**. The exchange collector raises fatally when Binance is enabled, and the exchange list
  (`config/symbols.py:TARGET_EXCHANGES`, `config/settings.py:EXCHANGE_CONFIG`) is hardcoded with no
  env override. To collect real data here, temporarily disable Binance/Bybit (set `enabled: False`
  and reduce `TARGET_EXCHANGES` to `okx`) and revert before committing.

### Pre-existing failures (NOT environment problems)
- CI is red on `main` and feature branches: `ruff check .` reports hundreds of lint errors, `mypy`
  reports many type errors, and `pytest` has ~3 failing tests (test/code drift, e.g. expected table
  `funding_rate_snapshots` vs actual `funding_model_snapshots`). ~327 tests pass.
- The `technical_indicators` pipeline stage crashes in `logic_layer/technical_indicators/repository.py`
  (`save_merged_klines` calls `.strftime()` on a pandas `Series` instead of `.dt.strftime()`), so the
  `/technical/indicators/*` endpoints return "No indicator data" until that code bug is fixed.
