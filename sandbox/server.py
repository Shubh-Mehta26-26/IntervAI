"""Dedicated container supervisor. Never import this module into the API/worker."""

import hmac
import json
import math
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GUARD = "/usr/local/bin/intervai-guard"
ROOT = Path("/tmp/executions")
LANGUAGES = {"python": "solution.py", "cpp": "solution.cpp", "java": "Main.java"}
OUTPUT_LIMIT = 32768
LOCK = threading.Lock()
JOBS = {}
SLOT = threading.Semaphore(1)


def process_tree_rss(pid):
    total = 0
    pending = [pid]
    while pending:
        current = pending.pop()
        try:
            fields = Path(f"/proc/{current}/status").read_text().splitlines()
            total += next((int(line.split()[1]) for line in fields if line.startswith("VmRSS:")), 0)
            pending.extend(int(value) for value in Path(f"/proc/{current}/task/{current}/children").read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            pass
    return total


def validate(payload):
    if not isinstance(payload, dict) or set(payload) - {"id", "language", "source", "tests", "time_ms", "memory_mb"}:
        raise ValueError("Invalid execution request")
    identifier = str(uuid.UUID(payload["id"]))
    if payload["language"] not in LANGUAGES:
        raise ValueError("Unsupported language")
    if not isinstance(payload["source"], str) or not 1 <= len(payload["source"].encode()) <= 32768:
        raise ValueError("Source must contain 1–32768 bytes")
    if not isinstance(payload["tests"], list) or not 1 <= len(payload["tests"]) <= 20:
        raise ValueError("Invalid tests")
    for case in payload["tests"]:
        if not isinstance(case, dict) or set(case) != {"input", "expected"}:
            raise ValueError("Invalid test fields")
        if any(not isinstance(value, str) or len(value.encode()) > 4096 for value in case.values()):
            raise ValueError("Test size limit exceeded")
    if type(payload["time_ms"]) is not int or not 100 <= payload["time_ms"] <= 3000:
        raise ValueError("Invalid time limit")
    if type(payload["memory_mb"]) is not int or not 32 <= payload["memory_mb"] <= 256:
        raise ValueError("Invalid memory limit")
    return identifier


def process(command, directory, deadline_seconds, memory_mb, cancel, compiling=False, java=False, stdin=""):
    """Supervise actual child usage; all child execution is behind the irreversible guard."""
    start = time.monotonic()
    address_mb = 1536 if java else memory_mb
    guarded = [GUARD, "compile" if compiling else "runtime", str(directory), str(address_mb),
               str(min(30, math.ceil(deadline_seconds) + 1)), *command]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(directory),
           "TMPDIR": str(directory), "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen(guarded, cwd=directory, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, close_fds=True)
    child.stdin.write(stdin.encode())
    child.stdin.close()
    streams = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    for name in output:
        pipe = getattr(child, name)
        os.set_blocking(pipe.fileno(), False)
        streams.register(pipe, selectors.EVENT_READ, name)
    status, usage, code = "COMPLETED", None, None
    try:
        while code is None:
            if cancel.is_set():
                status = "CANCELLED"
            elif time.monotonic() - start > deadline_seconds:
                status = "TIMEOUT"
            try:
                rss = process_tree_rss(child.pid)
                if rss > memory_mb * 1024:
                    status = "MEMORY_LIMIT"
            except (FileNotFoundError, ProcessLookupError):
                pass
            for key, _ in streams.select(0.01):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    streams.unregister(key.fileobj)
                else:
                    target = output[key.data]
                    if len(target) + len(chunk) > OUTPUT_LIMIT:
                        status = "OUTPUT_LIMIT"
                    target.extend(chunk[: max(0, OUTPUT_LIMIT - len(target))])
            if status != "COMPLETED":
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            pid, result, measured = os.wait4(child.pid, os.WNOHANG)
            if pid:
                usage, code = measured, os.waitstatus_to_exitcode(result)
                child.returncode = code
        # Kill any compiler descendants even when the leader exits successfully.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for key in list(streams.get_map().values()):
            try:
                chunk = os.read(key.fileobj.fileno(), OUTPUT_LIMIT + 1)
                target = output[key.data]
                if len(target) + len(chunk) > OUTPUT_LIMIT:
                    status = "OUTPUT_LIMIT"
                target.extend(chunk[: max(0, OUTPUT_LIMIT - len(target))])
            except BlockingIOError:
                pass
        if status == "COMPLETED" and code:
            status = "SYSTEM_ERROR" if code == 125 else "COMPILE_ERROR" if compiling else "RUNTIME_ERROR"
        return {"status": status, "stdout": output["stdout"].decode(errors="replace"),
                "stderr": output["stderr"].decode(errors="replace").replace(str(directory), "<workspace>"),
                "execution_time_ms": round((time.monotonic() - start) * 1000),
                "memory_kb": usage.ru_maxrss if usage else None}
    finally:
        streams.close()
        for name in output:
            getattr(child, name).close()
        if child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def execute(payload, cancel):
    ROOT.mkdir(exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix="job-", dir=ROOT))
    try:
        language = payload["language"]
        (directory / LANGUAGES[language]).write_text(payload["source"])
        compiler = None
        if language == "cpp":
            compiler = ["/usr/bin/g++", "-std=c++17", "-O2", "solution.cpp", "-o", "program"]
        elif language == "java":
            compiler = ["/usr/bin/javac", "-J-Xmx128m", "-J-XX:ActiveProcessorCount=1", "-J-XX:+UseSerialGC",
                        "-J-XX:-UseContainerSupport", "-J-XX:CompressedClassSpaceSize=32m", "-J-XX:ReservedCodeCacheSize=32m",
                        "-J-XX:MaxMetaspaceSize=128m", "-J-XX:-UsePerfData", "-proc:none", "Main.java"]
        if compiler:
            compiled = process(compiler, directory, 15, 256, cancel, compiling=True, java=language == "java")
            if compiled["status"] != "COMPLETED":
                return {**compiled, "tests_total": len(payload["tests"]), "tests_passed": 0, "cases": []}
        commands = {"python": ["/usr/local/bin/python", "-I", "-B", "solution.py"],
                    "cpp": [str(directory / "program")],
                    "java": ["/usr/bin/java", "-Xmx64m", "-Xss256k", "-XX:MaxMetaspaceSize=64m",
                             "-XX:ReservedCodeCacheSize=32m", "-XX:CompressedClassSpaceSize=32m",
                             "-XX:ActiveProcessorCount=1", "-XX:+UseSerialGC", "-XX:-UseContainerSupport", "-cp", ".", "Main"]}
        cases = []
        for test in payload["tests"]:
            result = process(commands[language], directory, payload["time_ms"] / 1000, payload["memory_mb"], cancel,
                             java=language == "java", stdin=test["input"])
            result["passed"] = result["status"] == "COMPLETED" and result["stdout"].split() == test["expected"].split()
            cases.append(result)
            if result["status"] != "COMPLETED":
                break
        return {"status": next((c["status"] for c in cases if c["status"] != "COMPLETED"), "COMPLETED"),
                "tests_total": len(payload["tests"]), "tests_passed": sum(c["passed"] for c in cases),
                "execution_time_ms": sum(c["execution_time_ms"] for c in cases),
                "memory_kb": max((c["memory_kb"] or 0 for c in cases), default=0), "cases": cases}
    finally:
        # Iterative, no symlink following, and restore directory permissions first.
        # Candidate chmod/deep nesting must not defeat cleanup or recurse our stack.
        pending = [(directory, False)]
        while pending:
            current, visited = pending.pop()
            if visited:
                current.rmdir()
                continue
            current.chmod(0o700)
            pending.append((current, True))
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((Path(entry.path), False))
                    else:
                        os.unlink(entry.path)


def readiness():
    with tempfile.TemporaryDirectory() as directory:
        result = process(["/usr/bin/true"], Path(directory), 1, 64, threading.Event())
    if result["status"] != "COMPLETED":
        raise RuntimeError("Landlock ABI 3 and seccomp are required")
    if not all(shutil.which(command) for command in ("python", "g++", "javac", "java")):
        raise RuntimeError("Missing compiler/runtime")
    return {"ready": True, "languages": list(LANGUAGES)}


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        key = os.environ.get("CODE_RUNNER_API_KEY", "")
        return not key or hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key)
    def log_message(self, *args):
        pass  # Never log source, test contents, or headers.

    def respond(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.authorized():
            return self.respond(401, {"error": "Unauthorized"})
        try:
            if self.path == "/health":
                return self.respond(200, readiness())
            self.respond(404, {"error": "Not found"})
        except Exception:  # noqa: BLE001 - readiness must fail closed for any control failure.
            self.respond(503, {"error": "Sandbox security controls unavailable"})

    def do_POST(self):
        if not self.authorized():
            return self.respond(401, {"error": "Unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 262144:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/cancel":
                identifier = str(uuid.UUID(payload["id"]))
                with LOCK:
                    entry = JOBS.get(identifier)
                    if entry:
                        entry["cancel"].set()
                return self.respond(200, {"cancelled": True})
            if self.path != "/execute":
                return self.respond(404, {"error": "Not found"})
            identifier = validate(payload)
            fingerprint = json.dumps(payload, sort_keys=True)
            with LOCK:
                # Completed cache makes a worker lease retry reuse the same execution.
                for key in list(JOBS):
                    if JOBS[key]["done"].is_set() and time.monotonic() - JOBS[key]["created"] > 600:
                        del JOBS[key]
                existing = JOBS.get(identifier)
                if existing and existing["fingerprint"] != fingerprint:
                    return self.respond(409, {"error": "Execution ID conflict"})
                owner = existing is None
                if owner:
                    if len(JOBS) >= 128:
                        return self.respond(503, {"error": "Runner capacity exceeded"})
                    JOBS[identifier] = {"fingerprint": fingerprint, "cancel": threading.Event(),
                                        "done": threading.Event(), "created": time.monotonic(), "result": None}
                entry = JOBS[identifier]
            if owner:
                try:
                    with SLOT:
                        readiness()
                        entry["result"] = execute(payload, entry["cancel"])
                except Exception:  # noqa: BLE001 - contain unexpected failures at the execution boundary.
                    entry["result"] = {"status": "SYSTEM_ERROR", "tests_total": len(payload["tests"]),
                                       "tests_passed": 0, "cases": [], "execution_time_ms": None, "memory_kb": None}
                finally:
                    entry["done"].set()
            else:
                entry["done"].wait(90)
            self.respond(200, entry["result"] or {"status": "SYSTEM_ERROR"})
        except (ValueError, KeyError, TypeError):
            self.respond(422, {"error": "Invalid execution request"})


if __name__ == "__main__":
    if os.environ.get("APP_ENV") == "production" and len(os.environ.get("CODE_RUNNER_API_KEY", "")) < 32:
        raise RuntimeError("Production requires a configured runner authentication key")
    readiness()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
