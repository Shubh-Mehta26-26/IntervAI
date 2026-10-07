"""Real attack/integration suite. Run ONLY inside the dedicated sandbox container."""
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def request(path, payload=None):
    raw = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if os.environ.get("CODE_RUNNER_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["CODE_RUNNER_API_KEY"]
    req = urllib.request.Request("http://127.0.0.1:8080" + path, data=raw, headers=headers)
    with urllib.request.urlopen(req, timeout=100) as response:
        return json.load(response)


def payload(source, language="python", expected="ok", input="", time_ms=1000, memory_mb=128):
    return {"id": str(uuid.uuid4()), "language": language, "source": source,
            "tests": [{"input": input, "expected": expected}], "time_ms": time_ms, "memory_mb": memory_mb}


def case(name, source, statuses, **kwargs):
    result = request("/execute", payload(source, **kwargs))
    assert result["status"] in statuses, (name, result)
    if result["status"] == "COMPLETED":
        assert result["tests_passed"] == result["tests_total"], (name, result)
    assert not list(Path("/tmp/executions").iterdir()), "Execution workspace leaked"
    print(json.dumps({"test": name, "status": result["status"], "passed": result["tests_passed"],
                      "execution_time_ms": result["execution_time_ms"], "memory_kb": result["memory_kb"]}), flush=True)


def blocked(expression):
    return "try:\n    " + expression + "\n    print('UNBLOCKED')\nexcept (OSError, PermissionError):\n    print('ok')\n"


def main():
    assert request("/health")["languages"] == ["python", "cpp", "java"]
    case("python accepted", "print(sum(map(int,input().split())))", {"COMPLETED"}, input="2 3\n", expected="5")
    case("cpp accepted", '#include <iostream>\nint main(){std::cout<<"ok";}', {"COMPLETED"}, language="cpp")
    case("java accepted", 'public class Main {public static void main(String[] args){System.out.println("ok");}}', {"COMPLETED"}, language="java")
    case("infinite loop", "while True: pass", {"TIMEOUT"}, time_ms=200)
    case("memory", "x=bytearray(512*1024*1024)", {"MEMORY_LIMIT", "RUNTIME_ERROR"}, memory_mb=64)
    case("network", "import socket\n"+blocked("socket.create_connection(('1.1.1.1',80),timeout=1)"), {"COMPLETED"})
    case("non Unix socketpair", "import socket\n"+blocked("socket.socketpair(socket.AF_INET,socket.SOCK_STREAM)"), {"COMPLETED"})
    case("forbidden filesystem", blocked("open('/etc/passwd').read()"), {"COMPLETED"})
    case("supervisor filesystem", blocked("open('/opt/runner/server.py').read()"), {"COMPLETED"})
    case("path traversal", blocked("open('../../etc/passwd').read()"), {"COMPLETED"})
    case("proc environment", blocked("open('/proc/1/environ').read()"), {"COMPLETED"})
    case("supervisor signal", "import ctypes,errno\nc=ctypes.CDLL(None,use_errno=True)\nr=c.tgkill(2147483647,2147483647,9)\nprint('ok' if r==-1 and ctypes.get_errno()==errno.EPERM else 'UNBLOCKED')", {"COMPLETED"})
    case("ephemeral namespace and nonroot", "import os\nprint('ok' if os.getpid()==1 and os.getppid()==0 and os.getuid()==10001 else 'UNISOLATED')", {"COMPLETED"})
    case("namespace escape", "import ctypes,errno\nc=ctypes.CDLL(None,use_errno=True)\nr=c.unshare(0x70020000)\nprint('ok' if r==-1 and ctypes.get_errno()==errno.EPERM else 'UNBLOCKED')", {"COMPLETED"})
    case("zero candidate capabilities", "import ctypes\nc=ctypes.CDLL(None,use_errno=True)\nh=(ctypes.c_uint32*2)(0x20080522,0)\nd=(ctypes.c_uint32*6)()\nr=c.capget(ctypes.byref(h),ctypes.byref(d))\nprint('ok' if r==0 and not any(d) else 'PRIVILEGED')", {"COMPLETED"})
    case("process group escape", "import os\n"+blocked("os.setpgid(0,0)"), {"COMPLETED"})
    case("cleanup permission tampering", "import os\nos.mkdir('nested');open('nested/file','w').write('x');os.chmod('nested',0);print('ok')", {"COMPLETED"})
    case("fork", "import os\n"+blocked("os.fork()"), {"COMPLETED"})
    case("fork bomb", "import os\nwhile True: os.fork()", {"RUNTIME_ERROR"})
    case("shell command", "import subprocess\n"+blocked("subprocess.run(['/bin/sh','-c','cat /etc/passwd'],check=True)"), {"COMPLETED"})
    case("environment scrub", "import os\nprint('ok' if not any(k in os.environ for k in ('AUTH_SECRET','DATABASE_URL','OPENAI_API_KEY','GEMINI_API_KEY')) else 'LEAK')", {"COMPLETED"})
    case("huge stdout", "while True: print('x'*10000)", {"OUTPUT_LIMIT"})
    case("huge stderr", "import sys\nwhile True: sys.stderr.write('x'*10000)", {"OUTPUT_LIMIT"})
    case("cpp compile error", "This is invalid C++", {"COMPILE_ERROR"}, language="cpp")
    case("java runtime error", "public class Main {public static void main(String[] args){throw new RuntimeException();}}", {"RUNTIME_ERROR"}, language="java")
    huge = payload("x"*32769)
    try:
        request("/execute", huge)
        raise AssertionError("Oversized source accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 422
        print('{"test":"oversized source","status":"REJECTED"}', flush=True)
    bad = payload("print('ok')")
    bad["path"] = "../../etc/passwd"
    try:
        request("/execute", bad)
        raise AssertionError("User controlled path accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 422
        print('{"test":"path injection","status":"REJECTED"}', flush=True)
    cancellable = payload("while True: pass", time_ms=3000)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(request, "/execute", cancellable)
        time.sleep(0.2)
        request("/cancel", {"id": cancellable["id"]})
        result = future.result()
        assert result["status"] == "CANCELLED", result
    assert not list(Path("/tmp/executions").iterdir())
    print('{"test":"cancellation and cleanup","status":"CANCELLED"}', flush=True)
    duplicate = payload("print('ok')")
    first = request("/execute", duplicate)
    second = request("/execute", duplicate)
    assert first == second
    print('{"test":"duplicate execution","status":"CACHED"}', flush=True)


if __name__ == "__main__":
    main()
