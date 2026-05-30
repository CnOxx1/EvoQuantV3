# Open Source Checklist

这份清单面向准备把 EvoQuant 放到 GitHub 公开仓库时的最后检查。

## 本轮已经处理

- 新增根目录 [README.md](README.md)，作为 GitHub 首页入口
- 新增根目录 `.gitignore`，忽略数据库、日志、缓存和 LaTeX 中间文件
- 把关键 Markdown 文档里的本机绝对路径改成了仓库内相对路径
- 当前未发现 `.env`、`*.pem`、`*.key` 这类常见本地密钥文件
- 已补 [LICENSE](LICENSE)，当前仓库使用 `GPL-3.0`

## 发布前建议再确认一次

1. 决定哪些长文档要保留公开
   - [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)
   - [INVESTOR_PITCH.md](INVESTOR_PITCH.md)
   - [papers](papers)
2. 确认本地运行产物不进仓库
   - `database/*.db`
   - `logs/`
   - `__pycache__/`
   - `papers/**` 下的 LaTeX 中间文件
3. 检查是否需要补环境变量示例
   - 当前配置依赖 [config/settings.py](config/settings.py) 中的环境变量
   - 如果准备给外部开发者直接运行，建议后续增加 `.env.example`
4. 再做一次内容审查
   - 是否有不想公开的研究结论、投资人话术或实验稿件
   - 是否有需要脱敏的路径、注释、测试数据或截图

## 建议的 GitHub 仓库信息

- 仓库名：`EvoQuant`
- 简介：`AI-ready crypto market data infrastructure for multi-source collection, quality gating, and market context assembly.`
- 推荐 topics：`crypto`, `quant`, `market-data`, `ai`, `sqlite`, `ccxt`

## 建议的下一步

1. 初始化 Git 仓库并检查首批待提交文件
2. 如需对外运行体验更完整，再补一个 `.env.example`
3. 后续可增加 GitHub Actions，至少自动跑 `pytest`
