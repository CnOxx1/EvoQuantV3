import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


class FakeProcess:
    def __init__(self, poll_results, pid: int):
        self._poll_results = list(poll_results)
        self._last_result = None
        self.pid = pid
        self.terminated = False
        self.killed = False

    def poll(self):
        if self.terminated or self.killed:
            return 0
        if self._poll_results:
            self._last_result = self._poll_results.pop(0)
        return self._last_result

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def test_resolve_modules_defaults_to_autostart_daemons():
    modules = main.resolve_modules()

    assert [module.name for module in modules] == [
        "exchange_data",
        "macro_data",
        "news_data",
        "event_calendar_data",
        "onchain_data",
        "alternative_data",
        "tokenomics_data",
        "options_data",
        "data_quality_audit",
        "perpetual_dex_data",
        "onchain_address_data",
        "dex_liquidity_data",
        "gas_network_data",
        "governance_data",
        "logic_pipeline",
        "api_server",
    ]


def test_resolve_modules_supports_commas_and_deduplicates():
    modules = main.resolve_modules(
        ["exchange_data,technical_indicators", "exchange_data", "news_data"]
    )

    assert [module.name for module in modules] == [
        "exchange_data",
        "technical_indicators",
        "news_data",
    ]


def test_build_command_uses_runner_and_default_args():
    spec = main.MODULE_INDEX["macro_data"]

    command = spec.build_command(python_executable="/usr/bin/python3")

    assert command == [
        "/usr/bin/python3",
        "-m",
        "data_layer.macro_data.runner",
        "--mode",
        "scheduler",
    ]


def test_alternative_data_is_registered_and_default():
    spec = main.MODULE_INDEX["alternative_data"]

    assert spec.runner_module == "data_layer.alternative_data.runner"
    assert spec.autostart is True
    assert "alternative_data" in main.DEFAULT_MODULE_NAMES


def test_event_calendar_and_onchain_are_registered_and_default():
    event_calendar_spec = main.MODULE_INDEX["event_calendar_data"]
    onchain_spec = main.MODULE_INDEX["onchain_data"]

    assert event_calendar_spec.runner_module == "data_layer.event_calendar_data.runner"
    assert onchain_spec.runner_module == "data_layer.onchain_data.runner"
    assert event_calendar_spec.autostart is True
    assert onchain_spec.autostart is True
    assert "event_calendar_data" in main.DEFAULT_MODULE_NAMES
    assert "onchain_data" in main.DEFAULT_MODULE_NAMES


def test_tokenomics_and_options_are_registered_and_default():
    tokenomics_spec = main.MODULE_INDEX["tokenomics_data"]
    options_spec = main.MODULE_INDEX["options_data"]

    assert tokenomics_spec.runner_module == "data_layer.tokenomics_data.runner"
    assert tokenomics_spec.autostart is True
    assert "tokenomics_data" in main.DEFAULT_MODULE_NAMES
    assert options_spec.runner_module == "data_layer.options_data.runner"
    assert options_spec.autostart is True
    assert "options_data" in main.DEFAULT_MODULE_NAMES


def test_data_quality_audit_is_registered_and_default():
    spec = main.MODULE_INDEX["data_quality_audit"]

    assert spec.runner_module == "data_layer.data_quality.runner"
    assert spec.autostart is True
    assert "data_quality_audit" in main.DEFAULT_MODULE_NAMES


def test_market_breadth_and_asset_readiness_are_registered_as_tasks():
    market_breadth_spec = main.MODULE_INDEX["market_breadth"]
    asset_readiness_spec = main.MODULE_INDEX["asset_readiness"]

    assert market_breadth_spec.runner_module == "logic_layer.market_breadth.runner"
    assert market_breadth_spec.kind == "task"
    assert market_breadth_spec.autostart is False

    assert asset_readiness_spec.runner_module == "logic_layer.asset_readiness.runner"
    assert asset_readiness_spec.kind == "task"
    assert asset_readiness_spec.autostart is False


def test_supervise_modules_returns_zero_for_successful_task(monkeypatch):
    task_spec = main.MODULE_INDEX["technical_indicators"]
    launched_children = []

    def fake_launch_module(spec, python_executable=None, extra_args=()):
        child = main.ManagedProcess(
            spec=spec,
            process=FakeProcess([0], pid=101),
        )
        launched_children.append(child)
        return child

    monkeypatch.setattr(main, "launch_module", fake_launch_module)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    exit_code = main.supervise_modules([task_spec], poll_interval_seconds=0.0)

    assert exit_code == 0
    assert launched_children[0].process.terminated is False


def test_restart_child_relaunches_daemon_within_limit(monkeypatch):
    spec = main.MODULE_INDEX["macro_data"]
    child = main.ManagedProcess(
        spec=spec,
        process=FakeProcess([1], pid=201),
        restart_count=0,
        last_started_at=datetime.now(),
    )
    relaunched = []

    def fake_launch_module(spec, python_executable=None, extra_args=()):
        new_child = main.ManagedProcess(
            spec=spec,
            process=FakeProcess([None], pid=202),
        )
        relaunched.append(new_child)
        return new_child

    monkeypatch.setattr(main, "launch_module", fake_launch_module)

    restarted = main._restart_child(child)

    assert restarted is not None
    assert restarted.restart_count == 1
    assert relaunched[0].spec.name == "macro_data"


def test_restart_child_disables_daemon_after_limit(monkeypatch):
    spec = main.MODULE_INDEX["macro_data"]
    child = main.ManagedProcess(
        spec=spec,
        process=FakeProcess([1], pid=301),
        restart_count=main.DAEMON_RESTART_LIMIT,
        last_started_at=datetime.now(),
    )

    monkeypatch.setattr(main, "launch_module", lambda *args, **kwargs: None)

    restarted = main._restart_child(child)

    assert restarted is None
    assert child.disabled_after_failure is True


def test_restart_child_resets_counter_after_restart_window(monkeypatch):
    spec = main.MODULE_INDEX["macro_data"]
    child = main.ManagedProcess(
        spec=spec,
        process=FakeProcess([1], pid=401),
        restart_count=main.DAEMON_RESTART_LIMIT,
        last_started_at=datetime.now() - main.DAEMON_RESTART_WINDOW - timedelta(seconds=1),
    )
    relaunched = []

    def fake_launch_module(spec, python_executable=None, extra_args=()):
        new_child = main.ManagedProcess(
            spec=spec,
            process=FakeProcess([None], pid=402),
        )
        relaunched.append(new_child)
        return new_child

    monkeypatch.setattr(main, "launch_module", fake_launch_module)

    restarted = main._restart_child(child)

    assert restarted is not None
    assert restarted.restart_count == 1
    assert child.disabled_after_failure is False


def test_supervise_modules_returns_nonzero_when_daemon_exceeds_restart_limit(monkeypatch):
    daemon_spec = main.MODULE_INDEX["macro_data"]
    original_limit = main.DAEMON_RESTART_LIMIT
    processes = [FakeProcess([1], pid=501), FakeProcess([1], pid=502)]
    launch_count = {"value": 0}

    def fake_launch_module(spec, python_executable=None, extra_args=()):
        process = processes[min(launch_count["value"], len(processes) - 1)]
        launch_count["value"] += 1
        return main.ManagedProcess(
            spec=spec,
            process=process,
            last_started_at=datetime.now(),
        )

    monkeypatch.setattr(main, "launch_module", fake_launch_module)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "DAEMON_RESTART_LIMIT", 1)

    exit_code = main.supervise_modules([daemon_spec], poll_interval_seconds=0.0)

    main.DAEMON_RESTART_LIMIT = original_limit
    assert exit_code == 1
