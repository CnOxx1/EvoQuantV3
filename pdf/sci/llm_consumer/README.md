# LLM consumer — market world model for public LLMs

Understanding-first protocol: Compiled world-model bundles vs Raw feeds for
public LLM consumers (GPT / DeepSeek / GLM class).

```bash
make paper-llm-consumer
# or: python -m pdf.sci.llm_consumer.eval
```

- Offline: `public-llm-compiled-follower` + diagnostic mocks
- Live (optional): set `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `GLM_API_KEY`
- Outputs: `pdf/tables/table_llm_*.csv`, `table_llm_understanding.csv`,
  `table_world_bundle_examples.json` (also copied under `pdf/icaif26/tables/`)
