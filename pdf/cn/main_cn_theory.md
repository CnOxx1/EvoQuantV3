# 编译市场信息集：世界模型质量、选择性预测与经济价值

**李国聪**  
中文理论稿（与英文正式稿 `pdf/sci/main_acwmi_sci.tex` 对齐）  
源公式吸收自原论文：`pdf/original/main_cn_pm.txt`

> **篇幅说明**：顶刊（JF/RFS）通常需要完整理论推导 + 识别 + 多套稳健性，正文常见远长于 5 页。  
> 当前仓库里曾出现过“5 页实证速写”，那是草稿压缩，**不能**当作可投稿终稿。  
> 本中文稿把原理论公式写回；英文稿 §Theory 已同步恢复 displayed equations。

---

## 1. 世界模型质量：宽度、稳定性、诚实性

**定义（宽度）** 设关键证据带数为 \(K\)，第 \(k\) 带达到 AI 可用门槛则 \(a_{k,t}=1\)：

\[
B_t=\frac{1}{K}\sum_{k=1}^{K}a_{k,t}.
\]

**定义（稳定性）** 令 \(d_{j,t}\) 为来源 \(j\) 的时效惩罚，\(\omega_j\) 为权重：

\[
U_t=\exp\!\Big(-\sum_{j=1}^{J}\omega_j d_{j,t}\Big).
\]

**定义（诚实性）** 令 \(m_{j,t}=1\) 表示不该进入主视图却被错误注入：

\[
H_t=1-\frac{1}{J}\sum_{j=1}^{J}m_{j,t}.
\]

生产基线：

\[
\mathrm{WMI}_t=B_t\times U_t\times H_t.
\]

层级宽度与连续诚实性：

\[
B^{\mathrm{hier}}_t=0.25\,B^{\mathrm{dom}}_t+0.35\,B^{\mathrm{band}}_t+0.40\,B^{\mathrm{asset}}_t,
\]

\[
H^{\mathrm{cont}}_t=\exp(-2c_t)\max\bigl(0,\,1-0.5(1-e_t)\bigr).
\]

## 2. 认识论观测对象

\[
O_{j,t}=(x_{j,t},\,\tau_{j,t},\,q_{j,t},\,g_{j,t},\,r_{j,t}).
\]

AI 消费的是带时间、质量、门控与角色的状态对象集合，而非平面特征矩阵。

## 3. 异步观测与时滞误差界

潜在状态 \(S_{t+1}=F(S_t,\eta_{t+1})\)。来源观测：

\[
X^{\mathrm{obs}}_{j,t}=h_j(S_{t-\ell_{j,t}})+\nu_{j,t}.
\]

若 \(h_j\) Lipschitz，则有滞后导致的重建误差界（时滞 + 噪声 + 缺失）：

\[
\|\widetilde S_t-S_t\|
\le C_1\sum_j\omega_j\ell_{j,t}
+C_2\sum_j\omega_j\|\nu_{j,t}\|
+C_3\sum_j\omega_j(1-z_{j,t}).
\]

## 4. 信息滤子与编译算子

\[
\mathcal{F}^{\mathrm{raw}}_t=\sigma\bigl(\{X^{\mathrm{obs}}_{j,\tau}:j\le J,\tau\le t\}\bigr),\qquad
\mathcal{F}^{\mathrm{AI}}_t=\sigma(W^{\mathrm{AI}}_t,D_t),
\]

\[
\Pi_t=B_t\circ M_t\circ A_t,\qquad
W^{\mathrm{AI}}_t=\Pi_t(\mathcal{F}^{\mathrm{raw}}_t).
\]

其中 \(A_t\) 对齐/快照，\(M_t\) 质量门控，\(B_t\) bundle 聚合（与宽度符号需依上下文区分）。

## 5. ECP、MIG 与因果 DAG

\[
\mathrm{ECP}_t=\mathbf{1}\{\mathrm{conf}_t>\bar c\}\,\mathbf{1}\{\mathrm{WMI}_t<w\},
\]

\[
\mathrm{MIG}^{(m)}_{k,t}=I(R^{(m)}_t;E_{k,t}\mid I^{(-k)}_t),
\]

\[
O_t\to W_t\to A_t,\quad M_t\to W_t,\quad M_t\to A_t,\quad C_t\to(W_t,A_t).
\]

识别优先依赖可观测可用性冲击 \(O_t\)，而非简单“加特征”。

## 6. 贝叶斯拒绝判断

动作集 \(\mathcal{A}=\{\mathrm{bullish},\mathrm{bearish},\mathrm{neutral},\mathrm{abstain}\}\)：

\[
a^\star_t=\arg\min_{a\in\mathcal{A}}\mathbb{E}[\ell(a,R_t)\mid W_t],
\]

当所有非弃权动作的期望损失都高于 \(c_{\mathrm{abs}}(W_t)\) 时选择弃权。

## 7. ACWMI 与解释质量

\[
\mathrm{ACWMI}_t
=\exp\!\left(
\frac{\sum_{i=1}^{5}\gamma_i(r_t)\log x_{i,t}}{\sum_{i=1}^{5}\gamma_i(r_t)}
\right),
\quad
x_t=(B^{\mathrm{hier}}_t,U_t,H^{\mathrm{cont}}_t,S_t,C_t).
\]

\[
\mathrm{EAR}_t=\frac{\#\{\text{绑定证据的判断}\}}{\#\{\text{总判断}\}},\quad
\mathrm{UCR}_t=1-\mathrm{EAR}_t,\quad
\mathrm{EV}_t=\frac{d(\Phi_t,\Phi_{t-1})}{1+d(W_t,W_{t-1})}.
\]

## 8. 与实证的分工

- **理论贡献**：§1–7 的对象、界、算子、识别与弃权规则（来自原论文）。  
- **项目角色**：EvoQuant 仅提供可计算实例与真实多带 PIT 识别实验室。  
- **英文正式稿**：`pdf/sci/main_acwmi_sci.tex`（含相同公式编号体系）。  
- **原论文全文**：`pdf/original/main_cn_pm.txt`（更长推导与制度讨论仍应以之为准继续吸收）。
