# 编译市场信息集：世界模型质量、选择性预测与加密资产经济价值

**李国聪**（面向 JF/RFS 的投稿取向说明稿）

> 英文正稿：`pdf/sci/main_acwmi_sci.tex` / `.pdf`

## 相对上一版的关键升级

1. **真实日收益**（Yahoo，10 币种，2024-08→2026-08）
2. **PIT**：信号只用 t 之前历史
3. **IS 冻结阈值**，OOS 评估
4. **强基线**：always-long / momentum / thick ungated / outage / cascade / WMI
5. **经济价值**：Sharpe、CRRA CE(γ=2)、最大回撤
6. **消融**：thin vs thick；leave-one-band-out
7. **识别**：收益正交的可用性冲击事件研究
8. **如实报告**：本样本 ACWMI **不**在 CE 上优于 thick ungated

## 当前可站得住的结论

- 厚世界 ≫ 薄世界（exchange-only）
- 去掉 exchange 带 CE 损失最大
- 机制信号 OOS 显著优于 always-long / momentum
- 可用性冲击使 WMI/ACWMI 显著下降且当日收益≈0
- AC 门控可实施（IS 冻结），但是否提升 CE 取决于样本与风险偏好

## 冲顶刊仍缺

多源多年 vintaged 档案 + 真实中断日志 + 分析师/LLM EAR-ECP + 更长样本外部有效性。

```bash
PYTHONPATH=. python3 pdf/sci/run_jf_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```
