"""Single-active-job execution with advisory timeouts and cancellable subprocesses."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from flowgraph.application.plugins import resolve_plugin_paths


class JobManager:
    """Bounded jobs, stateless workers, and supervised incremental session workers."""

    def __init__(
        self,
        workspace: Path,
        *,
        timeout: float = 120,
        max_result: int = 64 << 20,
        verbose: bool = False,
        plugins: Sequence[str | Path] = (),
    ):
        self.workspace = workspace
        self.timeout = timeout
        self.max_result = max_result
        self.verbose = verbose
        self.plugins = resolve_plugin_paths(plugins)
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.process: subprocess.Popen | None = None
        self.active: str | None = None
        self.closed = False
        self.threads: list[threading.Thread] = []
        self.sessions: dict[str, tuple[subprocess.Popen, tempfile.TemporaryDirectory, float]] = {}

    def _report_state(self, identifier: str, state: str) -> None:
        if self.verbose:
            print(f"[flowgraph] Execution {identifier}: {state}", file=sys.stderr, flush=True)

    def submit(
        self, workflow: dict, options: dict | None = None, timeout_seconds: float | None = None
    ) -> dict:
        timeout = self.timeout if timeout_seconds is None else timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or (timeout_seconds is not None and timeout > 86400)
        ):
            raise ValueError("timeout_seconds must be a finite number between 0 and 86400")
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
            job = {
                "id": identifier,
                "state": "running",
                "result": None,
                "error": None,
                "timed_out": False,
                "timeout_seconds": timeout,
                "progress": [],
                "node_results": [],
            }
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
                                argument
                                for path in self.plugins
                                for argument in ("--plugin", str(path))
                            ),
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
            self._report_state(identifier, "running")
            thread = threading.Thread(
                target=self._watch,
                args=(identifier, process, temporary, session_id, timeout),
                daemon=True,
            )
            self.threads = [item for item in self.threads if item.is_alive()]
            self.threads.append(thread)
            thread.start()
            return {**job, "node_results": [], "result_cursor": 0}

    def _watch(self, identifier, process, temporary, session_id=None, timeout=None) -> None:
        result = None
        error = None
        try:
            response = Path(temporary.name) / "response.json"
            progress_file = response.with_name("progress.jsonl")
            progress_offset = 0
            progress = {}
            result_bytes = 0

            def read_progress():
                nonlocal progress_offset, result_bytes
                if not progress_file.exists():
                    return
                with progress_file.open("rb") as stream:
                    stream.seek(progress_offset)
                    for line in stream:
                        if not line.endswith(b"\n"):
                            break
                        progress_offset += len(line)
                        event = json.loads(line)
                        if "node_result" in event:
                            result_bytes += len(line)
                            if result_bytes > self.max_result:
                                self._stop(process)
                                raise ValueError("Live node results exceed the server size limit")
                            with self.lock:
                                self.jobs[identifier]["node_results"].append(event["node_result"])
                        else:
                            progress[event["node_id"]] = event
                with self.lock:
                    self.jobs[identifier]["progress"] = list(progress.values())

            deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
            while process.poll() is None and (session_id is None or not response.is_file()):
                read_progress()
                if time.monotonic() >= deadline:
                    with self.lock:
                        job = self.jobs.get(identifier)
                        if job and job["state"] == "running" and not job["timed_out"]:
                            job["timed_out"] = True
                            self._report_state(
                                identifier, "running (timeout reached; worker retained)"
                            )
                time.sleep(0.02)
            read_progress()
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
                self._report_state(identifier, job["state"])
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

    def get(self, identifier: str, after: int = 0) -> dict:
        with self.lock:
            job = dict(self.jobs[identifier])
            results = job["node_results"]
            if after < 0 or after > len(results):
                raise ValueError("Invalid node result cursor")
            job["node_results"] = results[after:]
            job["result_cursor"] = len(results)
            return job

    def cancel(self, identifier: str) -> dict:
        with self.lock:
            job = self.jobs[identifier]
            if job["state"] == "running":
                self._stop(self.process)
                job["state"] = "cancelled"
                self._report_state(identifier, "cancelled")
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
