# LLM consumer — market world model for public LLMs

Understanding-first protocol: Compiled world-model bundles vs Raw feeds for
public LLM consumers (GPT / DeepSeek / GLM class).

```bash
make paper-llm-consumer
# or: python -m pdf.sci.llm_consumer.eval
```

- Offline: `public-llm-compiled-follower` + diagnostic mocks
- Live (optional): OpenAI-compatible gateway via `OPENAI_BASE_URL` +
  `OPENAI_API_KEY` (or `TEAMOROUTER_API_KEY` / vendor keys). Never commit keys.
  Example: `python -m pdf.sci.llm_consumer.eval --live-only --sample-n 100 --tag live --workers 6`
  Ungated ablation (same 100 days): `--treatments ungated --sample-n 100 --tag ungated100`
- Outputs: `pdf/tables/table_llm_*.csv` (+ `*_live.*` when `--tag live`),
  `table_llm_understanding.csv`, `table_world_bundle_examples.json`
  (also copied under `pdf/icaif26/tables/`). Transcripts are gitignored.
