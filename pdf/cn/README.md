# 中文论文包（`pdf/cn/`）

| 文件 | 说明 |
| --- | --- |
| **`main_cn_core.md` / `.pdf`** | **World-Model-First 核心重写稿**（主题对齐 `pdf/original/main_cn_core.pdf`，含实证与图 1–15） |
| `main_cn_jf.md` / `.pdf` | JF/RFS 风格完整中文稿（编译/SDF 接口表述） |
| `main_jf_rfs.pdf` | 英文完整稿镜像 |
| `main_cn_theory.md` | 理论公式摘录（较短） |

英文正式 TeX：`pdf/sci/main_jf_rfs.tex`  
原论文源材料：`pdf/original/main_cn_pm.txt`

## 生成

```bash
export DB_SPLIT_ENABLED=1
make paper-lab          # PIT → 实证 → 核心稿补图+PDF → SCI PDF
# 或仅核心稿：
make paper-core
```
