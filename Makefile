.PHONY: all test build

all: test build

test:
	uv run pytest

build:
	uv run python -m build --wheel --no-isolation