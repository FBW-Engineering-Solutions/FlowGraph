"""Bounded, single-active-job execution with cancellable native subprocesses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path


class JobManager:
    """Keep recent results in memory; each run gets a fresh Python interpreter."""

    def __init__(self, workspace: Path, *, timeout: float = 120, max_result: int = 64 << 20):
        self.workspace = workspace
        self.timeout = timeout
        self.max_result = max_result
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.process: subprocess.Popen | None = None
        self.active: str | None = None
        self.closed = False
        self.threads: list[threading.Thread] = []

    def submit(self, workflow: dict) -> dict:
        with self.lock:
            if self.closed:
                raise RuntimeError("Execution service is closed")
            if self.active is not None:
                raise RuntimeError("Another execution is active")
            while len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "state": "running", "result": None, "error": None}
            temporary = tempfile.TemporaryDirectory(prefix="flowgraph-job-")
            root = Path(temporary.name)
            try:
                (root / "request.json").write_text(json.dumps(workflow), encoding="utf-8")
                # Preserve import roots when the CLI runs from a source checkout and
                # the child changes working directory to the user's workspace.
                environment = os.environ.copy()
                environment["PYTHONPATH"] = os.pathsep.join(
                    str(Path(item or os.getcwd()).resolve()) for item in sys.path
                )
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "flowgraph.server.worker",
                        str(root / "request.json"),
                        str(root / "response.json"),
                    ],
                    cwd=self.workspace,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                temporary.cleanup()
                raise
            self.jobs[identifier] = job
            self.process = process
            self.active = identifier
            thread = threading.Thread(
                target=self._watch,
                args=(identifier, process, temporary),
                daemon=True,
            )
            self.threads = [item for item in self.threads if item.is_alive()]
            self.threads.append(thread)
            thread.start()
            return dict(job)

    def _watch(self, identifier, process, temporary) -> None:
        result = None
        error = None
        try:
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                self._stop(process)
                raise TimeoutError("Execution exceeded the server timeout") from None
            response = Path(temporary.name) / "response.json"
            if process.returncode != 0 or not response.is_file():
                raise RuntimeError(
                    f"Execution process exited without a result ({process.returncode})"
                )
            if response.stat().st_size > self.max_result:
                raise ValueError("Execution result exceeds the server size limit")
            result = json.loads(response.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise TypeError("Invalid execution response")
        except Exception as exception:  # noqa: BLE001 - convert process failures to job state
            error = str(exception)
        finally:
            temporary.cleanup()
        with self.lock:
            job = self.jobs.get(identifier)
            if job is not None and job["state"] == "running":
                job.update(
                    state="completed"
                    if error is None and result.get("status") == "ok"
                    else "failed",
                    result=result,
                    error=error,
                )
            if self.active == identifier:
                self.active = None
                self.process = None

    @staticmethod
    def _stop(process) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def get(self, identifier: str) -> dict:
        with self.lock:
            return dict(self.jobs[identifier])

    def cancel(self, identifier: str) -> dict:
        with self.lock:
            job = self.jobs[identifier]
            if job["state"] == "running":
                self._stop(self.process)
                job["state"] = "cancelled"
                self.active = None
                self.process = None
            return dict(job)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            if self.active is not None:
                self.cancel(self.active)
        for thread in self.threads:
            thread.join(timeout=5)
