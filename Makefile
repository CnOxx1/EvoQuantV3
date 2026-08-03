.PHONY: test lint format typecheck dev clean help paper-lab paper-smoke paper-pit paper-pdf paper-bootstrap test-paper

PYTHON ?= python
export PYTHONPATH := $(CURDIR)

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

test: ## 运行测试（排除已知慢模块）
	$(PYTHON) -m pytest tests/ -q --ignore=tests/tokenomics_data --ignore=tests/exchange_data --ignore=tests/onchain_data

test-all: ## 运行全部测试
	$(PYTHON) -m pytest tests/ -q

test-fast: ## 只运行集成测试和新模块测试
	$(PYTHON) -m pytest tests/integration tests/test_*.py -q

test-paper: ## 论文服务相关单元测试
	$(PYTHON) -m pytest tests/test_paper_lab.py tests/ai_market_context tests/time_slice -q

lint: ## 代码检查（ruff）
	$(PYTHON) -m ruff check .

format: ## 代码格式化（ruff）
	$(PYTHON) -m ruff format .

typecheck: ## 类型检查（mypy，仅 api/database/config）
	$(PYTHON) -m mypy api/ database/ config/ --ignore-missing-imports

dev: ## 启动开发环境（API + 数据采集）
	$(PYTHON) main.py

api: ## 仅启动 API 服务
	$(PYTHON) -m api.app --port 8000

modules: ## 列出已注册模块
	$(PYTHON) main.py --list-modules

validate: ## 语法检查所有 Python 文件
	find . -name "*.py" -not -path "./.venv/*" | xargs -P4 -I{} $(PYTHON) -c "import ast; ast.parse(open('{}').read())"

paper-smoke: ## 论文生产 API 冒烟（BandPIT / ACWMI / O_t）
	$(PYTHON) pdf/sci/paper_lab.py smoke

paper-bootstrap: ## 拉取多带历史档案（需可达交易所；本环境多为 OKX）
	$(PYTHON) pdf/sci/paper_lab.py bootstrap

paper-pit: ## 从 SQLite 历史重建 PIT 面板
	$(PYTHON) pdf/sci/paper_lab.py pit

paper-pdf: ## 编译 SCI/JF 稿 PDF
	$(PYTHON) pdf/sci/paper_lab.py pdf

paper-lab: ## 一键：PIT → JF 实证 → PDF（加 WITH_BOOTSTRAP=1 先采集）
	@if [ "$(WITH_BOOTSTRAP)" = "1" ]; then \
		$(PYTHON) pdf/sci/paper_lab.py all --with-bootstrap; \
	else \
		$(PYTHON) pdf/sci/paper_lab.py all; \
	fi

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
