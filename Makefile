.PHONY: setup lint format check test build clean

setup:
	pip install ruff pytest

lint:
	ruff check src/ tests/ scripts/

format:
	ruff format src/ tests/ scripts/

check: lint
	ruff format --check src/ tests/ scripts/
	python scripts/check_syntax.py

test:
	pytest tests/ -v

build:
ifdef VERSION
	python scripts/build.py --version $(VERSION)
else
	python scripts/build.py
endif

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
