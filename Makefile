.PHONY: all test build doc


all: test build

test:
	export KOKKOS_PREFIX=/home/fbw/repos/spack/opt/spack/linux-skylake/kokkos-5.1.1-iptledib3tkcegzwk7u2t7and3ehu4dq
	export LD_LIBRARY_PATH="$KOKKOS_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
	uv run --no-sync pytest

build:
	export KOKKOS_PREFIX=/home/fbw/repos/spack/opt/spack/linux-skylake/kokkos-5.1.1-iptledib3tkcegzwk7u2t7and3ehu4dq
	export CMAKE_PREFIX_PATH="$KOKKOS_PREFIX"
	export LD_LIBRARY_PATH="$KOKKOS_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
	export CMAKE_BUILD_PARALLEL_LEVEL=4
	export OMP_NUM_THREADS=2
	export OMP_PROC_BIND=false

	uv sync --extra dev --extra io  --extra ml --extra cosapp  --extra imagej  \
  --config-settings-package muscat:cmake.define.Muscat_ENABLE_Mmg=OFF \
  --config-settings-package muscat:cmake.define.Muscat_ENABLE_Parmmg=OFF
	uv run --no-sync python -m build --wheel --no-isolation

doc:
	uv run  --no-sync --with zensical zensical build -f zensical.toml

servedoc: doc
	uv run  --no-sync python -m http.server "$${PORT:-8000}" --directory site

lint:
	uv run ruff format  .
	uv run ruff check .