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
│   └── database_collector.py           # SQLite 数据库文件大小导出
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
# 1. 安装依赖
pip install prometheus_client

# 2. 启动 API（确认指标端点可用）
python -m api.app &
curl http://localhost:8000/metrics/prometheus

# 3. 启动监控栈
cd monitoring
docker compose -f docker-compose.monitoring.yml up -d

# 4. 访问 Grafana
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

## 预置仪表盘（3 个仪表盘，共 40 个面板）

### 1. System Overview（16 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Health Status | Stat | 整体健康状态（Healthy/Degraded/Unhealthy） |
| WMI Score | Gauge | 世界模型指数 0-100，红/黄/绿三色 |
| Active Modules | Stat | 当前运行中的模块数 |
| Stopped Modules | Stat | 已停止的模块数 |
| Total Restarts | Stat | 所有模块累计重启次数 |
| Database Total Size | Stat | 3 个 SQLite 数据库总大小 |
| API Request Rate | Time Series | 按 HTTP 状态码分组的请求速率 + 总速率 |
| Request Latency (P50/P95/P99) | Time Series | 请求延迟分位数趋势 |
| Requests In-Progress | Time Series | 当前并发请求数实时曲线 |
| Request Rate by Path (Top 10) | Time Series | 按路径分组的请求热度堆叠图 |
| Error Rate (4xx + 5xx) | Time Series | 客户端/服务端错误速率 |
| Module Status | Table | 模块名、状态、重启次数、运行时长 |
| Database Sizes | Bar Gauge | 各数据库文件大小对比 |
| WMI Score History | Time Series | WMI 评分历史趋势 |
| Process Memory Usage | Time Series | API 进程 RSS / Virtual 内存 |
| Process CPU & Open FDs | Time Series | CPU 使用率 + 打开文件描述符数 |

### 2. Pipeline Health（12 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Stale Domains | Stat | 过期域数量（红色阈值 ≥3） |
| Fresh Domains | Stat | 新鲜域数量 |
| Pipeline Last Duration | Stat | 管道最近一次执行时长 |
| Pipeline Phases (Errors) | Stat | 管道阶段错误率 |
| Domain Freshness Status Map | State Timeline | 12 个域的新鲜度状态时间线（颜色编码） |
| Domain Latency (seconds) | Time Series | 各域数据延迟趋势（12 条线） |
| Current Domain Latency | Bar Gauge | 当前各域延迟横向对比 |
| Domain Freshness Distribution | Pie Chart | Fresh/Acceptable/Stale/Unavailable 占比 |
| System Health History | State Timeline | 系统健康状态变化历史 |
| Pipeline Phase Duration (by module) | Time Series | 各模块阶段执行时长堆叠柱状图 |
| Pipeline Total Duration Trend | Time Series | 管道总时长 P50/P95 趋势 |
| Pipeline Executions (rate) | Time Series | 管道执行次数 + 成功/失败阶段速率 |

### 3. Market Alerts（12 个面板）

| 面板 | 类型 | 监控内容 |
|------|------|----------|
| Total Alerts (last 1h) | Stat | 最近 1 小时告警总数 |
| Critical Alerts (last 1h) | Stat | 最近 1 小时 Critical 级别告警 |
| Warning Alerts (last 1h) | Stat | 最近 1 小时 Warning 级别告警 |
| Info Alerts (last 1h) | Stat | 最近 1 小时 Info 级别告警 |
| Alerts by Type | Pie Chart | 按告警类型分布（环形图） |
| Alerts by Severity | Bar Gauge | 按严重度分布梯度条 |
| Alert Rate by Severity | Time Series | 按严重度的告警速率曲线 |
| Alert Rate Trend (all) | Time Series | 总告警速率 + 按类型分组趋势 |
| Cumulative Alerts (24h) | Time Series | 24 小时累计告警 + 各严重度 1h 增量 |
| Alert Rate by Type (Top 5) | Time Series | 按类型的告警速率 Top 5 堆叠柱状图 |
| Alerts (last 24h) | Stat | 24 小时告警总计 |
| Critical (last 24h) | Stat | 24 小时 Critical 告警总计 |

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

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| — | — | 无需额外环境变量配置，开箱即用 |

**Docker Compose 配置：**
- Prometheus: port 9090, 15s 抓取间隔, 30 天数据保留
- Grafana: port 3000, admin/evoquant 默认密码
- 使用 `host.docker.internal` 访问宿主机 8000 端口

## 对现有代码的影响

最小侵入设计，仅修改 3 个文件共 32 行代码：

- `api/app.py` (+5 行) — 注册中间件和路由
- `main.py` (+15 行) — 后台导出线程
- `logic_layer/logic_pipeline/service.py` (+12 行) — 管道计时
