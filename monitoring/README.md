# monitoring/ — EvoQuant 监控与可观测性

Prometheus 指标导出 + Grafana 可视化仪表盘，提供系统运行状态的实时观测能力。

## 目录结构

```text
monitoring/
├── __init__.py
├── metrics.py                          # 14 个 Prometheus 指标定义
├── middleware.py                       # FastAPI HTTP 请求指标中间件
├── collectors/
│   ├── module_collector.py             # 模块监督状态导出（状态/重启/Uptime）
│   ├── pipeline_collector.py           # 域新鲜度/延迟/WMI/健康状态导出
│   └── database_collector.py           # 数据库大小导出（SQLite 文件 / PostgreSQL 连接池）
├── exporters/
│   └── prometheus_endpoint.py          # /metrics/prometheus 端点
├── docker-compose.monitoring.yml       # Prometheus + Grafana 容器编排
├── prometheus/
│   └── prometheus.yml                  # 抓取配置（15s 间隔）
└── grafana/
    ├── provisioning/                   # 自动配置（数据源 + 仪表盘发现）
    └── dashboards/                     # 3 个预置 JSON 仪表盘
```

## 快速启动

```bash
# 1. 启动 PostgreSQL + 监控栈
cd monitoring
docker compose -f docker-compose.monitoring.yml up -d

# 2. 验证 PostgreSQL 就绪
docker exec evoquant-postgres pg_isready -U evoquant

# 3. 启动 API（确认指标端点可用）
cd /path/to/EvoQuant
python -m api.app &
curl http://localhost:8000/metrics/prometheus

# 4. 启动全系统（自动加载 .env）
python main.py

# 5. 访问 Grafana
#    http://localhost:3000  (admin / evoquant)
```

## 核心指标

| 指标名 | 类型 | 标签 | 含义 |
|--------|------|------|------|
| `evoquant_http_requests_total` | Counter | method, path, status | HTTP 请求总数 |
| `evoquant_http_request_duration_seconds` | Histogram | method, path | 请求延迟 |
| `evoquant_http_requests_in_progress` | Gauge | method | 当前并发请求数 |
| `evoquant_module_status` | Gauge | module, kind | 模块状态 (1=运行, 0=停止, -1=禁用) |
| `evoquant_module_restart_count` | Gauge | module | 模块重启次数 |
| `evoquant_module_uptime_seconds` | Gauge | module | 模块运行时长 |
| `evoquant_domain_latency_seconds` | Gauge | domain | 域数据延迟（秒） |
| `evoquant_domain_freshness_status` | Gauge | domain | 域新鲜度 (0=fresh, 1=acceptable, 2=stale, 3=unavailable) |
| `evoquant_wmi_score` | Gauge | — | 世界模型指数 (0-100) |
| `evoquant_health_status` | Gauge | — | 整体健康 (0=healthy, 1=degraded, 2=unhealthy) |
| `evoquant_pipeline_phase_duration_seconds` | Histogram | phase, module, status | 管道阶段执行时长 |
| `evoquant_pipeline_total_duration_seconds` | Histogram | — | 管道总执行时长 |
| `evoquant_database_size_bytes` | Gauge | database | 数据库文件大小 |
| `evoquant_market_alerts_total` | Counter | type, severity | 市场告警计数 |

## 预置仪表盘（3 个仪表盘，共 43 个面板）

### 1. System Overview（18 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Health Status | Stat | 整体健康状态（Healthy/Degraded/Unhealthy） |
| WMI Score | Gauge | 世界模型指数 0-100，红/黄/绿三色 |
| Active Modules | Stat | 当前运行中的模块数 |
| Stopped | Stat | 已停止的模块数（红色阈值 ≥1） |
| Restarts | Stat | 所有模块累计重启次数 |
| Uptime | Stat | 最长模块运行时长 |
| DB Size | Stat | 3 个 SQLite 数据库总大小 |
| API Request Rate | Time Series | 按 HTTP 状态码分组的请求速率（多轴、渐变填充） |
| Request Latency | Time Series | P50/P95/P99 延迟分位数（虚线参考线） |
| Concurrent Requests | Time Series | 当前并发请求数实时曲线 |
| Top Paths by Request Rate | Time Series | 按路径的请求速率 Top 10（堆叠柱状图） |
| Error Ratio (%) | Time Series | 错误率百分比（面积填充，红色阈值） |
| Module Status | Table | 模块名、状态、重启次数、运行时长（表格含排序） |
| Database Sizes | Bar Gauge | 各数据库文件大小对比（渐变色条） |
| WMI Score History | Time Series | WMI 评分历史趋势（面积填充） |
| Process Memory | Time Series | RSS / Virtual 内存双轴（MB 单位） |
| CPU Usage | Time Series | CPU 使用率百分比（面积渐变） |
| File Descriptors & GC | Time Series | 打开 FD 数 + GC 速率双轴 |

### 2. Pipeline Health（13 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Stale Domains | Stat | 过期域数量（红色阈值 ≥3） |
| Fresh | Stat | 新鲜域数量（绿色） |
| Acceptable | Stat | 可接受域数量（黄色） |
| Unavailable | Stat | 不可用域数量（红色） |
| Pipeline Duration (P50) | Stat | 管道执行时长中位数 |
| Phase Errors/min | Stat | 管道阶段错误速率 |
| Domain Freshness Timeline | State Timeline | 12 个域的新鲜度状态时间线（4 色编码） |
| Domain Latency | Time Series | 各域数据延迟趋势（表格图例含 mean/max） |
| Freshness Distribution | Pie Chart | Fresh/Acceptable/Stale/Unavailable 环形图 |
| Health Status History | State Timeline | 系统健康状态变化历史（3 色编码） |
| Pipeline Phase Duration | Time Series | 各模块阶段执行时长堆叠柱状图 |
| Pipeline Total Duration | Time Series | 管道总时长 P50/P95 趋势 |
| Current Domain Latency | Bar Gauge | 当前各域延迟横向对比（渐变色条） |

### 3. Market Alerts（12 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Alerts (1h) | Stat | 最近 1 小时告警总数 |
| Critical | Stat | 最近 1 小时 Critical 级别告警（红色） |
| Warning | Stat | 最近 1 小时 Warning 级别告警（橙色） |
| Info | Stat | 最近 1 小时 Info 级别告警（蓝色） |
| Alerts (24h) | Stat | 24 小时告警总计 |
| Alert Rate (/min) | Stat | 每分钟告警速率 |
| By Type | Pie Chart | 按告警类型分布（环形图 + 百分比） |
| By Severity | Bar Gauge | 按严重度分布梯度条（连续色带） |
| Rate by Severity | Time Series | 按严重度的告警速率曲线（颜色覆盖） |
| Alert Rate Trend | Time Series | 总告警速率 + 按类型分组趋势 |
| Cumulative Alerts | Time Series | 24 小时累计告警 + 各严重度 1h 增量 |
| Alert Rate by Type (Stacked) | Time Series | 按类型的告警速率堆叠柱状图 |

## 架构设计

**采集链路：**
- FastAPI 中间件 → HTTP 请求指标（每次请求自动记录）
- main.py 后台线程（15s 循环）→ 模块状态指标
- /metrics/prometheus 后台线程（15s 循环）→ 域延迟、WMI、数据库大小
- logic_pipeline 阶段回调 → 管道执行时长

**优雅降级：**
- 所有监控代码用 `try/except ImportError` 保护
- 如果 `prometheus_client` 未安装，系统正常运行，只是不导出指标
- 如果 Docker Compose 未启动，`/metrics/prometheus` 端点仍可访问（用于调试）
- 现有 `/metrics` JSON 端点不受影响

## 配置

### PostgreSQL 数据库（Docker 容器）

Docker Compose 集成了 PostgreSQL 16 作为生产数据库：

```bash
# 启动 PostgreSQL + 监控栈
cd monitoring
docker compose -f docker-compose.monitoring.yml up -d

# 验证 PostgreSQL 就绪
docker exec evoquant-postgres pg_isready -U evoquant

# 运行 Alembic 迁移建表
cd /path/to/EvoQuant
alembic upgrade head
```

**PostgreSQL 三 Schema 映射：**

| Schema | 原 SQLite 文件 | 内容 |
|--------|---------------|------|
| `exchange_data` | exchange_data.db | K线、ticker、资金费率、盘口深度 |
| `market_data` | market_data.db | 稳定币、DeFi 清算、巨鲸组合 |
| `analytics` | analytics.db | 技术指标、合并K线 |

**切换后端：** 设置环境变量 `DB_BACKEND=postgres` 即可切换（默认 sqlite）。

### 监控服务

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| — | — | 监控模块无需额外环境变量，开箱即用 |

**Docker Compose 配置：**
- PostgreSQL: port 5432, evoquant/evoquant2024, 三 schema 自动初始化
  - `max_connections=200`（支持 30+ 并发模块各自独立连接池）
  - `idle_in_transaction_session_timeout=60s`（自动清理泄漏的空闲事务）
- Prometheus: port 9090, 15s 抓取间隔, 30 天数据保留
- Grafana: port 3000, admin/evoquant 默认密码
- 使用 `host.docker.internal` 访问宿主机 8000 端口

## 对现有代码的影响

最小侵入设计，仅修改 3 个文件共 32 行代码：

- `api/app.py` (+5 行) — 注册中间件和路由
- `main.py` (+15 行) — 后台导出线程
- `logic_layer/logic_pipeline/service.py` (+12 行) — 管道计时
