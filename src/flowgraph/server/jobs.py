"""Bounded, single-active-job execution with cancellable native subprocesses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path


class JobManager:
    """Bounded jobs, stateless workers, and supervised incremental session workers."""

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
        self.sessions: dict[str, tuple[subprocess.Popen, tempfile.TemporaryDirectory, float]] = {}

    def submit(self, workflow: dict, options: dict | None = None) -> dict:
        with self.lock:
            if self.closed:
                raise RuntimeError("Execution service is closed")
            if self.active is not None:
                raise RuntimeError("Another execution is active")
            session_id = None
            if options is not None:
                if not isinstance(options, dict):
                    raise ValueError("options must be an object")
                session_id = options.get("session_id")
                if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
                    raise ValueError("session_id must be text between 1 and 128 characters")
            for key, (worker, directory, used) in list(self.sessions.items()):
                if worker.poll() is not None or time.monotonic() - used > 1800:
                    self._stop(worker)
                    directory.cleanup()
                    del self.sessions[key]
            while len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "state": "running", "result": None, "error": None}
            temporary = tempfile.TemporaryDirectory(prefix="flowgraph-job-")
            root = Path(temporary.name)
            try:
                (root / "request.json").write_text(
                    json.dumps(
                        workflow if options is None else {"workflow": workflow, "options": options}
                    ),
                    encoding="utf-8",
                )
                # Preserve import roots when the CLI runs from a source checkout and
                # the child changes working directory to the user's workspace.
                environment = os.environ.copy()
                environment["PYTHONPATH"] = os.pathsep.join(
                    str(Path(item or os.getcwd()).resolve()) for item in sys.path
                )
                session_root = None
                if session_id in self.sessions:
                    process, session_root, _ = self.sessions[session_id]
                else:
                    if session_id is not None:
                        while len(self.sessions) >= 4:
                            key = min(self.sessions, key=lambda key: self.sessions[key][2])
                            worker, directory, _ = self.sessions.pop(key)
                            self._stop(worker)
                            directory.cleanup()
                        session_root = tempfile.TemporaryDirectory(prefix="flowgraph-session-")
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "flowgraph.server.worker",
                            *(
                                ["--session", session_root.name]
                                if session_root
                                else [str(root / "request.json"), str(root / "response.json")]
                            ),
                        ],
                        cwd=self.workspace,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                if session_id is not None:
                    self.sessions[session_id] = (process, session_root, time.monotonic())
                    command = Path(session_root.name) / "command.json"
                    pending = command.with_suffix(".tmp")
                    pending.write_text(
                        json.dumps(
                            {
                                "request": str(root / "request.json"),
                                "response": str(root / "response.json"),
                            }
                        ),
                        encoding="utf-8",
                    )
                    pending.replace(command)
            except Exception:
                temporary.cleanup()
                raise
            self.jobs[identifier] = job
            self.process = process
            self.active = identifier
            thread = threading.Thread(
                target=self._watch,
                args=(identifier, process, temporary, session_id),
                daemon=True,
            )
            self.threads = [item for item in self.threads if item.is_alive()]
            self.threads.append(thread)
            thread.start()
            return dict(job)

    def _watch(self, identifier, process, temporary, session_id=None) -> None:
        result = None
        error = None
        try:
            response = Path(temporary.name) / "response.json"
            if session_id is not None:
                deadline = time.monotonic() + self.timeout
                while not response.is_file() and process.poll() is None:
                    if time.monotonic() >= deadline:
                        self._stop(process)
                        raise TimeoutError("Execution exceeded the server timeout")
                    time.sleep(0.02)
            else:
                try:
                    process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    self._stop(process)
                    raise TimeoutError("Execution exceeded the server timeout") from None
            if (session_id is None and process.returncode != 0) or not response.is_file():
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
            if session_id in self.sessions and process.poll() is not None:
                worker, directory, _ = self.sessions[session_id]
                if worker is process:
                    del self.sessions[session_id]
                    directory.cleanup()

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
            for process, directory, _ in self.sessions.values():
                self._stop(process)
                directory.cleanup()
            self.sessions.clear()
        for thread in self.threads:
            thread.join(timeout=5)

    def dispose_session(self, session_id: str) -> None:
        """Dispose an idle session; active execution must be cancelled first."""
        with self.lock:
            entry = self.sessions.get(session_id)
            if entry is None:
                return
            process, directory, _ = entry
            if self.active is not None and self.process is process:
                raise RuntimeError("Cannot dispose an active execution session")
            del self.sessions[session_id]
            self._stop(process)
            directory.cleanup()
