# LLM consumer validation

Secondary experiment for the JF/RFS paper: **within-model** Compiled vs Raw information sets.

- Protocol (pre-registered): [`protocol.md`](protocol.md)
- Frozen prompts: `prompts/frozen/`
- Action schema: `schemas/action.json`
- Offline providers: `providers/mock.py`
- Runner: `python -m pdf.sci.llm_consumer.eval` or `make paper-llm-consumer`

This harness does **not** replace PIT/LOBO identification. Commercial API providers can be added later behind the same `LLMProvider` protocol without changing the scientific design.
