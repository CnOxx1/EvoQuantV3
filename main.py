from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Iterable, Sequence

from loguru import logger

from config.logging import setup_logger
from config.settings import validate_config

PROJECT_ROOT = str(Path(__file__).resolve().parent)


@dataclass(frozen=True)
class ModuleSpec:
    """后端模块注册信息。新增模块时优先在这里补一条配置。"""

    name: str
    runner_module: str
    description: str
    kind: str = "daemon"
    default_args: tuple[str, ...] = ()
    autostart: bool = False

    def build_command(
        self,
        python_executable: str | None = None,
        extra_args: Sequence[str] = (),
    ) -> list[str]:
        executable = python_executable or sys.executable
        return [
            executable,
            "-m",
            self.runner_module,
            *self.default_args,
            *extra_args,
        ]


@dataclass
class ManagedProcess:
    spec: ModuleSpec
    process: subprocess.Popen
    handled_exit: bool = False
    restart_count: int = 0
    last_started_at: datetime | None = None
    disabled_after_failure: bool = False


MODULE_REGISTRY: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        name="exchange_data",
        runner_module="data_layer.exchange_data.runner",
        description="交易所基础数据采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="macro_data",
        runner_module="data_layer.macro_data.runner",
        description="宏观跨市场因子采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="news_data",
        runner_module="data_layer.news_data.runner",
        description="新闻数据采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="event_calendar_data",
        runner_module="data_layer.event_calendar_data.runner",
        description="未来事件日历采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="onchain_data",
        runner_module="data_layer.onchain_data.runner",
        description="链上资金行为采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="alternative_data",
        runner_module="data_layer.alternative_data.runner",
        description="补充特征采集与调度",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="tokenomics_data",
        runner_module="data_layer.tokenomics_data.runner",
        description="供给压力、解锁与基金会钱包流向采集",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="options_data",
        runner_module="data_layer.options_data.runner",
        description="期权波动率曲面与持仓结构采集",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="data_quality_audit",
        runner_module="data_layer.data_quality.runner",
        description="跨模块真实数据质量审计与市场世界模型巡检",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="perpetual_dex_data",
        runner_module="data_layer.perpetual_dex_data.runner",
        description="永续 DEX 数据采集（dYdX/Hyperliquid/GMX funding 和成交量）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="onchain_address_data",
        runner_module="data_layer.onchain_address_data.runner",
        description="链上地址画像采集（Arkham/Etherscan 巨鲸地址和资金流）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="dex_liquidity_data",
        runner_module="data_layer.dex_liquidity_data.runner",
        description="DEX 流动性采集（Uniswap V3/Curve 池 TVL 和 tick 分布）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="gas_network_data",
        runner_module="data_layer.gas_network_data.runner",
        description="Gas 和网络状态采集（Etherscan/Blocknative）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="governance_data",
        runner_module="data_layer.governance_data.runner",
        description="DAO 治理投票采集（Snapshot/Tally 提案和投票）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="prediction_market_data",
        runner_module="data_layer.prediction_market_data.runner",
        description="预测市场数据采集（Polymarket 概率与交易量）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="onchain_holder_data",
        runner_module="data_layer.onchain_holder_data.runner",
        description="链上持有者数据采集（MVRV/SOPR/NUPL 与持有者分布）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="liquid_staking_data",
        runner_module="data_layer.liquid_staking_data.runner",
        description="流动性质押数据采集（Lido/RocketPool/EigenLayer）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="mempool_data",
        runner_module="data_layer.mempool_data.runner",
        description="BTC 内存池数据采集（mempool.space 压力与大额交易）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="funding_round_data",
        runner_module="data_layer.funding_round_data.runner",
        description="VC 融资轮次采集（DefiLlama raises）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="exchange_reserve_data",
        runner_module="data_layer.exchange_reserve_data.runner",
        description="交易所储备数据采集（BTC/ETH/USDT 储备与净流动）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="miner_data",
        runner_module="data_layer.miner_data.runner",
        description="矿工数据采集（算力/难度/Puell Multiple/矿工收入）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="derivatives_sentiment_data",
        runner_module="data_layer.derivatives_sentiment_data.runner",
        description="衍生品情绪采集（恐惧贪婪/多空比/OI/杠杆率）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="stablecoin_flow_data",
        runner_module="data_layer.stablecoin_flow_data.runner",
        description="稳定币链上事件流采集（mint/burn/跨链净流）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="token_unlock_realtime",
        runner_module="data_layer.token_unlock_realtime.runner",
        description="代币解锁实时监控（TokenUnlocks API）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="cex_orderbook_depth",
        runner_module="data_layer.cex_orderbook_depth.runner",
        description="交易所深度盘口采集（5000 档全量）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="whale_wallet_pnl",
        runner_module="data_layer.whale_wallet_pnl.runner",
        description="巨鲸钱包 PnL 跟踪（DeBank/Arkham）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="nft_market_data",
        runner_module="data_layer.nft_market_data.runner",
        description="NFT 市场数据采集（Reservoir/Blur）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="defi_liquidation_data",
        runner_module="data_layer.defi_liquidation_data.runner",
        description="DeFi 清算事件采集（Aave/Compound subgraph）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="dex_trade_flow",
        runner_module="data_layer.dex_trade_flow.runner",
        description="DEX 大单交易流采集（0x/1inch）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="cross_chain_messaging",
        runner_module="data_layer.cross_chain_messaging.runner",
        description="跨链消息协议采集（LayerZero/Wormhole/Axelar）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="lending_utilization",
        runner_module="data_layer.lending_utilization.runner",
        description="借贷协议利用率采集（Aave/Compound/Morpho）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="search_trend_data",
        runner_module="data_layer.search_trend_data.runner",
        description="搜索趋势数据采集（Google Trends）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="exchange_announcement",
        runner_module="data_layer.exchange_announcement.runner",
        description="交易所公告采集（Binance/OKX/Bybit 上币下币维护）",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="logic_pipeline",
        runner_module="logic_layer.logic_pipeline.runner",
        description="逻辑层全链路定时编排：自动执行特征计算→标准化→跨资产→风险→AI上下文",
        kind="daemon",
        default_args=("--mode", "scheduler"),
        autostart=True,
    ),
    ModuleSpec(
        name="technical_indicators",
        runner_module="logic_layer.technical_indicators.runner",
        description="技术指标合并与计算任务",
        kind="task",
        default_args=("--mode", "all"),
        autostart=False,
    ),
    ModuleSpec(
        name="exchange_comparison",
        runner_module="logic_layer.exchange_comparison.runner",
        description="交易所横向对比任务",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="market_breadth",
        runner_module="logic_layer.market_breadth.runner",
        description="跨资产市场广度快照任务",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="asset_readiness",
        runner_module="logic_layer.asset_readiness.runner",
        description="资产级真实证据可用性矩阵任务",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="ai_market_context",
        runner_module="logic_layer.ai_market_context.runner",
        description="AI 最终市场上下文聚合任务",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="cross_asset_analysis",
        runner_module="logic_layer.cross_asset_analysis.runner",
        description="跨资产相关性、相对强弱、板块轮动、资金流向分析",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="portfolio_risk",
        runner_module="logic_layer.portfolio_risk.runner",
        description="组合风险度量：波动率、集中度、分散化评分",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="feature_standardization",
        runner_module="logic_layer.feature_standardization.runner",
        description="特征标准化：Z-score、百分位、跨资产排名与维度复合信号",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="time_slice",
        runner_module="logic_layer.time_slice.runner",
        description="时间切片查询：查看任意历史时刻的全市场特征快照",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="news_sentiment",
        runner_module="logic_layer.news_sentiment.runner",
        description="新闻情感标注：对新闻进行情感/事件类型/影响范围分类",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="pipeline_latency",
        runner_module="logic_layer.pipeline_latency.runner",
        description="数据管道延迟追踪：暴露各域端到端数据新鲜度指标",
        kind="task",
        autostart=False,
    ),
    ModuleSpec(
        name="api_server",
        runner_module="api.app",
        description="对外 REST API 服务：为 AI 消费者提供结构化市场数据接口",
        kind="daemon",
        autostart=True,
    ),
)
MODULE_INDEX = {spec.name: spec for spec in MODULE_REGISTRY}
DEFAULT_MODULE_NAMES = tuple(spec.name for spec in MODULE_REGISTRY if spec.autostart)
DAEMON_RESTART_LIMIT = 3
DAEMON_RESTART_WINDOW = timedelta(minutes=15)
DAEMON_RESTART_BASE_DELAY = float(os.environ.get("DAEMON_RESTART_BASE_DELAY", "2.0"))
DAEMON_RESTART_MAX_DELAY = float(os.environ.get("DAEMON_RESTART_MAX_DELAY", "60.0"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="后端模块总入口")
    parser.add_argument(
        "--modules",
        nargs="*",
        help=(
            "指定要启动的模块名，支持空格或逗号分隔。"
            "默认启动当前已标记 autostart 的常驻模块。"
        ),
    )
    parser.add_argument(
        "--list-modules",
        action="store_true",
        help="列出当前已注册模块",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印启动命令，不真正拉起模块",
    )
    return parser


def normalize_module_names(raw_names: Sequence[str] | None) -> list[str]:
    names: list[str] = []
    for raw_name in raw_names or ():
        for item in raw_name.split(","):
            name = item.strip()
            if name:
                names.append(name)
    return names


def resolve_modules(selected_names: Sequence[str] | None = None) -> list[ModuleSpec]:
    module_names = normalize_module_names(selected_names)
    if not module_names:
        module_names = list(DEFAULT_MODULE_NAMES)

    if not module_names:
        raise ValueError("当前没有配置默认启动模块，请先补充 MODULE_REGISTRY")

    resolved: list[ModuleSpec] = []
    seen: set[str] = set()

    for module_name in module_names:
        spec = MODULE_INDEX.get(module_name)
        if spec is None:
            available = ", ".join(MODULE_INDEX)
            raise ValueError(f"未知模块: {module_name}，可选值: {available}")
        if module_name in seen:
            continue
        resolved.append(spec)
        seen.add(module_name)

    return resolved


def format_module_list() -> str:
    lines = ["已注册模块："]
    for spec in MODULE_REGISTRY:
        start_mode = "默认启动" if spec.autostart else "手动启动"
        lines.append(
            f"- {spec.name} [{spec.kind}] {start_mode}: {spec.description}"
        )
    return "\n".join(lines)


def launch_module(
    spec: ModuleSpec,
    python_executable: str | None = None,
    extra_args: Sequence[str] = (),
) -> ManagedProcess:
    command = spec.build_command(
        python_executable=python_executable,
        extra_args=extra_args,
    )
    logger.info(f"启动模块 {spec.name}: {' '.join(command)}")
    process = subprocess.Popen(command, cwd=PROJECT_ROOT)
    return ManagedProcess(
        spec=spec,
        process=process,
        last_started_at=datetime.now(),
    )


def _restart_child(
    child: ManagedProcess,
    *,
    python_executable: str | None = None,
) -> ManagedProcess | None:
    now = datetime.now()
    last_started_at = child.last_started_at
    within_restart_window = (
        last_started_at is not None
        and (now - last_started_at) <= DAEMON_RESTART_WINDOW
    )
    next_restart_count = child.restart_count + 1 if within_restart_window else 1

    if next_restart_count > DAEMON_RESTART_LIMIT:
        logger.error(
            "模块 {} 在 {} 分钟内已连续退出 {} 次，停止自动重启并保留其他模块继续运行",
            child.spec.name,
            int(DAEMON_RESTART_WINDOW.total_seconds() // 60),
            DAEMON_RESTART_LIMIT,
        )
        child.disabled_after_failure = True
        return None

    # 指数退避延迟：base * 2^(count-1)，上限 max_delay
    delay = min(
        DAEMON_RESTART_BASE_DELAY * (2 ** (next_restart_count - 1)),
        DAEMON_RESTART_MAX_DELAY,
    )
    logger.warning(
        "模块 {} 意外退出，{:.1f}s 后进行第 {} 次自动重启",
        child.spec.name,
        delay,
        next_restart_count,
    )
    time.sleep(delay)

    restarted = launch_module(
        child.spec,
        python_executable=python_executable,
    )
    restarted.restart_count = next_restart_count
    return restarted


def stop_modules(
    children: Iterable[ManagedProcess],
    timeout_seconds: float = 10.0,
):
    alive_children: list[ManagedProcess] = []

    # 第一步：发送 SIGINT 让子进程优雅退出（处理 atexit/finally）
    for child in children:
        if child.process.poll() is not None:
            continue
        logger.info(f"停止模块 {child.spec.name} [pid={child.process.pid}]")
        try:
            child.process.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError):
            continue
        alive_children.append(child)

    # 等待一半超时时间让 SIGINT 生效
    half_timeout = timeout_seconds / 2
    deadline = time.monotonic() + half_timeout
    while alive_children and time.monotonic() < deadline:
        alive_children = [
            child for child in alive_children if child.process.poll() is None
        ]
        if alive_children:
            time.sleep(0.2)

    # 第二步：仍存活的发 SIGTERM
    for child in alive_children:
        try:
            child.process.terminate()
        except (ProcessLookupError, OSError):
            continue

    deadline = time.monotonic() + half_timeout
    while alive_children and time.monotonic() < deadline:
        alive_children = [
            child for child in alive_children if child.process.poll() is None
        ]
        if alive_children:
            time.sleep(0.2)

    # 第三步：强制 kill
    for child in alive_children:
        logger.warning(
            f"模块 {child.spec.name} 在 {timeout_seconds:.0f}s 内未退出，执行强制 kill"
        )
        try:
            child.process.kill()
        except ProcessLookupError:
            continue


def _start_metrics_exporter(children: list) -> None:
    """启动后台线程，每 15 秒导出模块状态到 Prometheus 指标。"""
    try:
        from monitoring.collectors.module_collector import export_module_status
    except ImportError:
        return

    from threading import Thread

    def _loop():
        while True:
            try:
                export_module_status({mp.spec.name: mp for mp in children})
            except Exception:
                pass
            time.sleep(15)

    Thread(target=_loop, daemon=True, name="metrics-exporter").start()


def supervise_modules(
    module_specs: Sequence[ModuleSpec],
    python_executable: str | None = None,
    poll_interval_seconds: float = 1.0,
) -> int:
    shutdown_requested = Event()
    exit_code = 0
    children = [
        launch_module(spec, python_executable=python_executable)
        for spec in module_specs
    ]

    # 启动 Prometheus 模块状态导出线程（优雅降级）
    _start_metrics_exporter(children)

    previous_handlers = {}

    def handle_signal(signum, frame):
        signame = signal.Signals(signum).name
        logger.info(f"收到信号 {signame}，准备停止所有模块...")
        shutdown_requested.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, handle_signal)

    try:
        while True:
            active_count = 0

            for index, child in enumerate(children):
                if child.disabled_after_failure:
                    continue

                return_code = child.process.poll()
                if return_code is None:
                    active_count += 1
                    continue

                if child.handled_exit:
                    continue
                child.handled_exit = True

                if shutdown_requested.is_set():
                    continue

                if child.spec.kind == "task" and return_code == 0:
                    logger.info(f"任务模块 {child.spec.name} 已执行完成")
                    continue

                if child.spec.kind == "daemon":
                    logger.error(
                        f"常驻模块 {child.spec.name} 意外退出，返回码={return_code}"
                    )
                    restarted = _restart_child(
                        child,
                        python_executable=python_executable,
                    )
                    if restarted is not None:
                        children[index] = restarted
                        active_count += 1
                        continue
                    exit_code = max(exit_code, return_code or 1)
                else:
                    logger.error(
                        f"任务模块 {child.spec.name} 执行失败，返回码={return_code}"
                    )
                    exit_code = return_code or 1
                    shutdown_requested.set()
                    break

            if shutdown_requested.is_set():
                break
            if active_count == 0:
                return exit_code

            time.sleep(poll_interval_seconds)

        return exit_code
    finally:
        stop_modules(children)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main():
    args = build_parser().parse_args()
    setup_logger("main")

    # 启动时校验配置合理性
    config_warnings = validate_config()
    if config_warnings:
        logger.warning("启动时发现 {} 条配置告警，请检查环境变量", len(config_warnings))

    if args.list_modules:
        print(format_module_list())
        return

    try:
        module_specs = resolve_modules(args.modules)
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("加密货币量化系统 - 总入口启动")
    logger.info("=" * 60)
    logger.info(f"本次模块选择: {', '.join(spec.name for spec in module_specs)}")

    if args.dry_run:
        for spec in module_specs:
            print(" ".join(spec.build_command()))
        return

    sys.exit(supervise_modules(module_specs))


if __name__ == "__main__":
    main()
