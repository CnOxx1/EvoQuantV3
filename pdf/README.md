# EvoQuant 论文参考与理论扩展

本目录存放项目相关学术论文、SCI 投稿稿、以及由项目代码生成的图/表。

## 文件结构

```text
pdf/
  main_cn_core.pdf              # 前序论文（World-Model-First / WMI）
  main_cn_acwmi.md|.txt|.pdf    # 中文理论优化稿
  main_cn_acwmi_sci.pdf         # SCI 英文稿（含图表）副本
  figures/                      # Fig.1–Fig.8
  tables/                       # Table CSV / panel data
  sci/
    main_acwmi_sci.tex          # Elsevier elsarticle 源稿
    main_acwmi_sci.pdf          # SCI 英文 PDF
    run_paper_experiments.py    # 实验与出图脚本
    generate_sci_pdf.py         # PDF 渲染脚本
    README.md
```

## 理论演进

1. **第一代**：\(\mathrm{WMI}=B\times U\times H\)
2. **第二代（本文）**：RCA-WM / 加权几何 \(\mathrm{ACWMI}\)
   - 层级宽度、连续诚实性、信号完整性、跨证据一致性
   - 体制–任务条件化编译、点时路径、降级韧性诚实性

## 复现图表

```bash
PYTHONPATH=. python3 pdf/sci/run_paper_experiments.py
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```

关键实证结果（示意，以脚本最新输出为准）：

- 因子分解模型 \(R^2=0.484\) vs 标量 WMI \(R^2=0.115\)
- 危机体制下 ACWMI 拒绝判断率远高于 WMI 固定阈值
