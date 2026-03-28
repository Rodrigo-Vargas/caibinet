.PHONY: install test lint

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	ruff check . && mypy .
