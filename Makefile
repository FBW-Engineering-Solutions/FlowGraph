.PHONY: all test build doc

all: test build

test:
	uv run pytest

build:
	uv run python -m build --wheel --no-isolation

doc:
	uv run --with zensical zensical build -f zensical.toml

servedoc: doc
	uv run python -m http.server "$${PORT:-8000}" --directory site
