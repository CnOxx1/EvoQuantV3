# Core 基类抽象层

为数据层和逻辑层提供统一的基类模板，消除 40+ 模块中的重复代码。新模块继承基类后只需实现业务逻辑。

## 组件

| 基类 | 职责 | 子类需实现 |
|------|------|-----------|
| `BaseDataClient` | HTTP 客户端（retry + 熔断 + 限流） | `base_url`, `_build_headers()` |
| `BaseDataService` | 数据层 Service 模板 | `_init_tables()`, `_do_collect()`, `_build_context_bundle()` |
| `BaseDataRunner` | 数据层 CLI（bootstrap/once/scheduler） | `MODULE_NAME`, `SERVICE_CLASS` |
| `BaseAnalyticsRepository` | 逻辑层 Repository | `TABLE_NAME`, `COLUMNS` |
| `BaseAnalyticsService` | 逻辑层 Service 模板 | `_get_repositories()`, `_compute()` |
| `BaseAnalyticsRunner` | 逻辑层 CLI（--run/--print-context） | `MODULE_NAME`, `SERVICE_CLASS` |

## BaseDataClient 内置能力

- **熔断器**：连续 5 次失败 → 60s 开路，之后半开探测
- **限流器**：令牌桶算法，可配置 QPS
- **重试**：指数退避（3 次），可配置 backoff 系数
- **超时**：全局请求超时 + 连接超时分离

## 使用示例

```python
from core import BaseDataService, BaseDataRunner

class MyDataService(BaseDataService):
    MODULE_NAME = "my_module"

    def _init_tables(self, db):
        db.execute("CREATE TABLE IF NOT EXISTS ...")

    def _do_collect(self, db, symbols):
        # 采集逻辑
        pass

    def _build_context_bundle(self, db):
        return {"status": "ok"}

class MyDataRunner(BaseDataRunner):
    MODULE_NAME = "my_module"
    SERVICE_CLASS = MyDataService

if __name__ == "__main__":
    MyDataRunner().run()
```

## CLI 参数

数据层 Runner：
- `--mode bootstrap` — 全量历史回填
- `--mode once` — 单次采集
- `--mode scheduler` — 定时循环（默认）
- `--interval N` — 调度间隔秒数

逻辑层 Runner：
- `--run` — 执行分析
- `--print-context` — 输出 AI 上下文 bundle（JSON）
