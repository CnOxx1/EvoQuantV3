# basis

## 当前职责

- 计算 `basis_abs`
- 计算 `basis_bps`
- 计算 `annualized_basis_bps`

## 目标

让 AI 理解永续合约相对现货的定价偏离。

## 维护约束

- `timestamp` 和 `next_funding_time` 必须先统一标准化成 UTC naive `datetime` 再参与年化计算。
- 如果 `funding_timestamp` 缺失或无法解析，这一行 `basis` 必须直接跳过，不能再回退成本地当前时间去伪装 freshness。
- 如果只有 `next_funding_time` 坏掉，该行仍应保留真实 `spot / mark / funding_rate / basis_bps`，但 `annualized_basis_bps` 必须降级为空。
- `raw_payload_json` 现在还会保留 `component_timestamp_gap_seconds / component_timestamp_gap_status / annualization_status / next_funding_time_status` 这些诊断字段，方便下游判断这条 basis 是“完整可用”还是“仅原始参考”。
- 这里修的是时间语义，不是补值逻辑；如果上游没有真实 `spot / mark / funding` 字段，`basis` 仍然应该保持缺失，而不是伪造结果。
