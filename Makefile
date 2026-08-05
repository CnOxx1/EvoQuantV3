.PHONY: test lint format typecheck dev clean help paper-lab paper-smoke paper-pit paper-pdf paper-full paper-ai-wm paper-icaif26 paper-icaif26-see paper-core paper-bootstrap paper-llm-consumer paper-reconcile test-paper

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

test-paper: ## 论文服务相关单元测试（含 JF 识别不变量与 LLM consumer）
	$(PYTHON) -m pytest tests/test_paper_lab.py tests/test_jf_inference.py tests/test_jf_identification.py tests/test_jf_extras.py tests/test_jf_theory_align.py tests/test_paper_e2e.py tests/test_raw_pit_and_reconcile.py tests/test_llm_consumer.py tests/test_scoped_wmi_handoff.py tests/ai_market_context tests/time_slice -q

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

paper-smoke: ## 论文生产 API 冒烟（BandPIT / ACWMI / O_t / scoped handoff）
	$(PYTHON) pdf/sci/paper_lab.py smoke

paper-scoped-handoff: ## 重建 scoped-WMI 开阀占比 + Compiled-open 交接表
	$(PYTHON) pdf/sci/paper_lab.py scoped-handoff

paper-bootstrap: ## 拉取多带历史档案（需可达交易所；本环境多为 OKX）
	$(PYTHON) pdf/sci/paper_lab.py bootstrap

paper-pit: ## 从 SQLite 历史重建 PIT 面板
	$(PYTHON) pdf/sci/paper_lab.py pit

paper-pdf: ## 编译 SCI/JF 稿 PDF
	$(PYTHON) pdf/sci/paper_lab.py pdf

paper-full: ## 生成完整顶刊工作论文 PDF（英+中；含 AI-WM 变体）
	$(PYTHON) pdf/sci/generate_full_manuscript_pdf.py --variant both

paper-ai-wm: ## AI-for-finance 世界模型运行时叙事 PDF → pdf/sci/main_ai_world_model.pdf
	$(PYTHON) pdf/sci/generate_full_manuscript_pdf.py --variant ai-wm --skip-chinese

paper-icaif26: ## ICAIF '26 Paper A（pdf/icaif26/main.pdf；refusal-primary ranking）
	cd pdf/icaif26 && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	cd pdf/icaif26 && bibtex main >/dev/null || true
	cd pdf/icaif26 && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	cd pdf/icaif26 && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	test -f pdf/icaif26/main.pdf
	cp pdf/icaif26/main.pdf pdf/icaif26/main_icaif26.pdf
	@echo "Wrote pdf/icaif26/main.pdf (ACM sigconf anonymous)"

paper-icaif26-see: ## ICAIF '26 Paper B（pdf/icaif26_see/main.pdf；see-market spine）
	cd pdf/icaif26_see && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	cd pdf/icaif26_see && bibtex main >/dev/null || true
	cd pdf/icaif26_see && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	cd pdf/icaif26_see && pdflatex -interaction=nonstopmode main.tex >/dev/null || true
	test -f pdf/icaif26_see/main.pdf
	cp pdf/icaif26_see/main.pdf pdf/icaif26_see/main_icaif26_see.pdf
	@echo "Wrote pdf/icaif26_see/main.pdf (ACM sigconf anonymous; see-market)"

paper-core: ## World-Model-First 核心中文稿：补图 + PDF
	$(PYTHON) pdf/sci/generate_core_figures.py
	$(PYTHON) pdf/sci/generate_core_manuscript_pdf.py

paper-reconcile: ## Yahoo vs 交易所收益对账审计
	$(PYTHON) pdf/sci/reconcile_returns.py

paper-llm-consumer: ## Compiled vs Raw AI-consumer 验证（默认 mock，无 API key）
	$(PYTHON) -m pdf.sci.llm_consumer.eval

paper-lab: ## 一键：PIT → JF 实证 → LLM consumer → 核心稿 PDF（加 WITH_BOOTSTRAP=1 先采集）
	@if [ "$(WITH_BOOTSTRAP)" = "1" ]; then \
		$(PYTHON) pdf/sci/paper_lab.py all --with-bootstrap; \
	else \
		$(PYTHON) pdf/sci/paper_lab.py all; \
	fi
	$(PYTHON) pdf/sci/generate_core_figures.py
	$(PYTHON) pdf/sci/generate_core_manuscript_pdf.py

clean: ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
