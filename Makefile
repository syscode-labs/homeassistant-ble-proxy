.PHONY: help lint lint-python lint-yaml lint-markdown format install install-hooks test clean

help:
	@echo "Available targets:"
	@echo "  lint          - Run all linters"
	@echo "  lint-python   - Run Ruff on Python files"
	@echo "  lint-yaml     - Run yamllint on YAML files"
	@echo "  lint-markdown - Run markdownlint on Markdown files"
	@echo "  format        - Auto-format Python files with Ruff"
	@echo "  install       - Install development dependencies"
	@echo "  install-hooks - Install pre-commit hooks including commit-msg stage"
	@echo "  test          - Run tests"
	@echo "  clean         - Remove build artifacts"

lint: lint-python lint-yaml lint-markdown

lint-python:
	ruff check pi-fallback/

lint-yaml:
	yamllint -c .yamllint.yaml .

lint-markdown:
	markdownlint-cli2 "**/*.md"

format:
	ruff check --fix pi-fallback/
	ruff format pi-fallback/

install:
	pip install ruff yamllint markdownlint-cli2 pre-commit
	pre-commit install

install-hooks:
	pre-commit install --hook-type commit-msg

test:
	cd pi-fallback && python -m pytest -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
