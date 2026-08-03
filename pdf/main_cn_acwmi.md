# 编译市场信息集（理论写回说明）

**李国聪**

## 直接回答两个问题

1. **原论文理论公式去哪了？**  
   此前英文 5 页稿把 §Theory 压成一段话，displayed equations 丢失。  
   现已写回：
   - 英文 TeX：`pdf/sci/main_acwmi_sci.tex`（§Theory，含 WMI / \(O_{j,t}\) / 时滞界 / \(\Pi_t\) / ECP / MIG / DAG / 弃权 / ACWMI / EAR·UCR·EV）
   - 中文理论稿：`pdf/cn/main_cn_theory.md`
   - 原论文全文：`pdf/original/main_cn_pm.txt`

2. **5 页真的可以过吗？**  
   **不能。** 对 JF/RFS 来说，5 页实证速写远不够；连一般应用类 SCI 全文也偏短。  
   5 页稿只适合当作“实验室进度备忘”，不是投稿终稿。

## 真实 PIT 实证摘要（仍有效）

厚世界 CE 0.47 vs 薄世界 −0.01；LOBO ΔCE：macro/alt/exchange ≈ −0.53/−0.53/−0.34；  
IS-frozen ACWMI Sharpe 0.90 / CE 0.20。

## 复现

```bash
make paper-lab
PYTHONPATH=. python3 pdf/sci/generate_sci_pdf.py
```
