# open_interest

## 当前职责

- 采集 `open_interest_contracts`
- 采集 `open_interest_usd`

## 目标

让 AI 看见行情是否伴随加杠杆扩仓。

## 当前约束

- 上游 `timestamp` 会统一标准化成 UTC-naive
- 如果 `timestamp` 缺失或损坏，会直接跳过该行，不会回退成当前时间伪装成最新快照
- 即使 source 级通过 AI-ready，bundle 仍会继续做行级过滤；既没有 `open_interest_usd` 也没有 `open_interest_contracts` 的真实行只会保留在 `raw_open_interest`
