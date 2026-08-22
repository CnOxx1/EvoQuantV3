# EvoQuant Intelligence Console 的 SQLite 复用边界

## 结论

本地部署采用 **一个 SQLite 数据体系、三个既有数据域文件** 的方式。市场行情、宏观与链上数据、分析指标继续由 EvoQuant 写入其现有数据库；管理后台在 `analytics.db` 中写入独立的 `admin_*` 工作区表。因此本地运行 **不需要安装 MySQL 服务**，也不会复制或迁移已有行情数据。

| SQLite 文件 | 既有职责 | 后台使用方式 | 是否由后台重建 |
|---|---|---|---|
| `database/exchange_data.db` | 交易所行情、资金费率、持仓量、订单簿等高频快照 | 作为真实市场数据来源，只读复用 | 否 |
| `database/market_data.db` | 宏观、新闻、链上、代币经济学、事件与期权等低频数据 | 作为扩展研究数据来源，只读复用 | 否 |
| `database/analytics.db` | 技术指标、组合风险、特征标准化与数据质量等逻辑层输出 | 在同一文件中新增带 `admin_` 前缀的工作区表 | 仅幂等创建缺失的后台表 |

## 管理后台表

所有管理后台表均以 `admin_` 为前缀，以避免和数据采集、逻辑层输出或 API 查询表混淆。`admin_users`、`admin_teams`、`admin_team_members` 与 `admin_team_invitations` 保存 OAuth 身份和团队权限；`admin_watchlists` 与 `admin_watchlist_assets` 保存研究团队的资产范围；`admin_research_briefs`、`admin_brief_assets`、`admin_risk_alerts` 和 `admin_ingest_events` 保存可追溯简报、风险事件及幂等投递记录；其余表承担连接配置、反馈、API Key 与使用量审计。

> `admin_ingest_events` 对 `(team_id, event_id)` 建有唯一约束。若本地闭环任务因网络或进程故障重试同一事件，后台会拒绝重复写入，避免重复生成简报或风险提醒。

## 初始化命令

在 Windows PowerShell 中进入 EvoQuantV3 项目目录，并确保已激活原有 Python 虚拟环境后执行：

```powershell
.\.venv\Scripts\python.exe scripts\init_admin_workspace.py
```

脚本会先执行带版本记录的 `20260821_admin_workspace_v1` 迁移，再输出目标文件、14 张 `admin_*` 表、SQLite 外键状态及 WAL 日志模式。迁移状态保存于 `evoquant_schema_migrations`；重复执行安全：它只会报告已应用状态或补齐缺失表和索引，不会删除、清空或重建任一已有数据表。

如需核验指定副本，可显式传入路径：

```powershell
.\.venv\Scripts\python.exe scripts\init_admin_workspace.py --database "C:\Users\limu\Desktop\量化学习\EvoQuantV3\database\analytics.db"
```

## 本地后台环境变量

管理后台的 `.env` 需要设置 `EVOQUANT_SQLITE_PATH` 指向同一个 `analytics.db` 文件。其他 OAuth 变量保持原有 Manus OAuth 配置即可。

```dotenv
EVOQUANT_SQLITE_PATH=C:\Users\limu\Desktop\量化学习\EvoQuantV3\database\analytics.db
VITE_APP_ID=NmhJ7f9w3tmhJtmisBWe6k
OAUTH_SERVER_URL=https://api.manus.im
VITE_OAUTH_PORTAL_URL=https://manus.im
```

在该变量存在时，后台会自动使用 SQLite 适配层；未设置时，云端部署仍沿用其原有 MySQL/TiDB 配置。因此本地开发与云端试点可以共享同一套界面和业务契约，而无需互相覆盖数据库设置。

## 并发与安全边界

EvoQuant 和管理后台均会为 SQLite 启用 WAL、外键约束和 30 秒忙等待。Python 数据采集器继续持有行情与分析写入职责；Node 管理后台只对 `admin_*` 表写入，并从现有域表读取真实数据。这样可降低锁竞争，也确保管理层操作不会污染原始市场数据。
