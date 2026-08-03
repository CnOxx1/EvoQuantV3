# 编译市场信息集（真实多带 PIT 版）

**李国聪** — 面向 JF/RFS 的说明稿

> 本文件位于中文论文包：`pdf/cn/`。  
> 正式投稿以英文稿为准：`pdf/sci/main_acwmi_sci.tex` / `pdf/sci/main_acwmi_sci.pdf`。  
> 原论文可复用源材料：`pdf/original/`。  
> 复现入口：`pdf/sci/README.md`（`make paper-lab`）；中文 PDF：`python3 pdf/cn/generate_cn_pdf.py`。

## 本轮完成

- 多带历史库灌入（OKX + macro + alternative 等）
- `build_pit_archive.py` 从历史表构建 400 天 PIT（优先走生产 `BandPITService`）
- `run_pit_jf_experiments.py` 重做识别与经济价值
- 项目侧 paper lab：`BandPITService`、`load_availability_shocks`、可配置 WMI/ACWMI
- 论文按真实 PIT 结果改写

## 关键结论

1. **厚世界 ≫ 薄世界**（CE 0.47 vs −0.01）  
2. **LOBO**：去掉 macro/alternative/exchange，CE 分别 −0.53 / −0.53 / −0.34  
3. **ACWMI** 可 IS 冻结实施（Sharpe 0.90），但本样本 CE 仍低于 thick ungated  
4. **生产 WMI&lt;0.2** 在稀疏档案上 100% 弃权 → 阈值必须按信息集支撑冻结  
5. `time_slice` 可历史取 klines；分析快照仍稀，PIT 主路径走原始历史表 / `band_readiness`

## 复现

```bash
make paper-smoke
make paper-lab
make paper-lab WITH_BOOTSTRAP=1
```

生产接口：`BandPITService`（多带 PIT）、`load_availability_shocks`（\(O_t\)）、
`WORLD_MODEL_INDEX_MODE` / `ACWMI_ABSTAIN_THRESHOLD`（WMI/ACWMI）。

## 仍缺（冲顶刊）

持续采集使 news/onchain/options 不再右删失；每日落 readiness 快照；真实中断日志作 \(O_t\)。
