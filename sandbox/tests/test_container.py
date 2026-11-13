"""The code sandbox against a REAL container (TMDEV-242): the negative controls.

test_daemon.py proves the run loop. This file proves the claims the threat
model makes: that hostile code run through the real service definition cannot
read the database or secrets, reach a network, write outside its scratch
folder, forge or read the spool, escape its limits, or stop the daemon.

Opt-in: it starts two throwaway containers, so it skips unless
TUBEMATIC_SANDBOX_IT_IMAGE names an image holding /app/sandbox/daemon.py,
tubematic_core and mcp/sandbox_client.py (the backend image of this branch, or
a thin layer over a test image, see docs/developer/test-suites/sandbox.md).

    TUBEMATIC_SANDBOX_IT_IMAGE=tmdev242-sandbox-it:latest pytest sandbox/tests/test_container.py

The sandbox container is built from the `tubematic-sandbox` service in
docker-compose.yml itself (every isolation flag is read from it), so a flag
dropped from compose is a failure here. A second container plays tubematic-mcp
(root, default capabilities, the same spool mounted at /sandbox) and submits
requests through mcp/sandbox_client.py. Both are removed by exact name.
CPU only: no GPU, no network, no volume other than a temporary spool.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import yaml

IMAGE = os.environ.get("TUBEMATIC_SANDBOX_IT_IMAGE", "")
SANDBOX = "tmdev242-sandbox-it"
MCP = "tmdev242-mcp-it"
REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(not IMAGE or not shutil.which("docker"),
                                reason="set TUBEMATIC_SANDBOX_IT_IMAGE to run against a real container")


def docker(*args, check=True, timeout=180, input=None):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, input=input)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}: {r.stderr.strip()}")
    return r


def _compose_run_args(spool: str) -> list[str]:
    """`docker run` flags for the tubematic-sandbox service, read from compose."""
    svc = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]["tubematic-sandbox"]
    args = ["--network", svc["network_mode"], "--cpus", str(svc["cpus"]), "--memory", svc["mem_limit"],
            "--pids-limit", str(svc["pids_limit"])]
    if svc.get("read_only"):
        args.append("--read-only")
    for t in svc.get("tmpfs", []):
        args += ["--tmpfs", t]
    for c in svc.get("cap_drop", []):
        args += ["--cap-drop", c]
    for c in svc.get("cap_add", []):
        args += ["--cap-add", c]
    for o in svc.get("security_opt", []):
        args += ["--security-opt", o]
    for e in svc.get("environment", []):
        args += ["-e", e]
    args += ["-v", f"{spool}:/spool"]
    return [*args, IMAGE, *svc["command"].split()]


@pytest.fixture(scope="module")
def box():
    spool = tempfile.mkdtemp(prefix="tmdev242-spool-")
    os.chmod(spool, 0o755)
    for name in (SANDBOX, MCP):
        docker("rm", "-f", name, check=False)
    docker("run", "-d", "--name", SANDBOX, *_compose_run_args(spool))
    docker("run", "-d", "--name", MCP, "--network", "none", "-v", f"{spool}:/sandbox",
           "-e", "TUBEMATIC_SANDBOX_DIR=/sandbox", "--entrypoint", "sleep", IMAGE, "infinity")
    deadline = time.time() + 30
    while time.time() < deadline:
        r = docker("exec", MCP, "python3", "-c",
                   "import sys; sys.path[:0]=['/app/lib','/app/mcp']\n"
                   "from tubematic_core import sandbox_protocol as P\n"
                   "a = P.heartbeat_age('/sandbox'); print(a is not None and a < 5)", check=False)
        if r.stdout.strip() == "True":
            break
        time.sleep(0.5)
    else:
        logs = docker("logs", SANDBOX, check=False)
        raise RuntimeError(f"the sandbox never beat: {logs.stdout} {logs.stderr}")
    yield spool
    docker("rm", "-f", SANDBOX, MCP, check=False)
    # the spool holds root-owned folders: remove them from inside a container
    docker("run", "--rm", "--network", "none", "-v", f"{spool}:/s", "--entrypoint", "rm", IMAGE, "-rf",
           "/s/req", "/s/done", "/s/heartbeat", check=False)
    shutil.rmtree(spool, ignore_errors=True)


_DRIVER = """
import json, sys
sys.path[:0] = ['/app/lib', '/app/mcp']
import sandbox_client as sc
lang, timeout = sys.argv[1], float(sys.argv[2])
code = sys.stdin.read()
print(json.dumps(sc.run_snippet('/sandbox', lang, code, timeout) or {"unavailable": True}))
"""


def run(code, language="python", timeout=10):
    """One run through the MCP side of the spool, as MCP does it."""
    r = docker("exec", "-i", MCP, "python3", "-c", _DRIVER, language, str(timeout), input=code, timeout=120)
    return json.loads(r.stdout.strip().splitlines()[-1])


def probe(code, language="python", timeout=10):
    """Run code that prints one JSON object; return it."""
    res = run(code, language, timeout)
    assert not res.get("unavailable") and res["exit_code"] == 0, json.dumps(res)
    return json.loads(res["stdout"])


# ── the container itself ─────────────────────────────────────────────────────

def test_the_container_has_the_isolation_compose_asks_for(box):
    info = json.loads(docker("inspect", SANDBOX).stdout)[0]
    hc = info["HostConfig"]
    assert hc["NetworkMode"] == "none" and hc["ReadonlyRootfs"] is True and hc["Privileged"] is False
    assert hc["CapDrop"] == ["ALL"] and "no-new-privileges:true" in hc["SecurityOpt"]
    assert [m["Destination"] for m in info["Mounts"]] == ["/spool"]
    assert not any("docker.sock" in m["Source"] for m in info["Mounts"])
    assert info["Config"]["Env"] and not any(k in " ".join(info["Config"]["Env"]) for k in ("KEY", "TOKEN", "SECRET"))
    assert hc["PidsLimit"] <= 512 and hc["Memory"] > 0 and hc["NanoCpus"] > 0


# ── what the code is ─────────────────────────────────────────────────────────

IDENTITY = """
import json, os
caps = [l for l in open('/proc/self/status') if l.startswith(('CapEff', 'CapPrm', 'CapAmb', 'CapInh'))]
print(json.dumps({"uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(),
                  "caps": [l.split()[1] for l in caps], "env": sorted(os.environ),
                  "nnp": [l.split()[1] for l in open('/proc/self/status') if l.startswith('NoNewPrivs')]}))
"""


def test_the_code_runs_as_nobody_with_no_capabilities_and_a_scrubbed_environment(box):
    r = probe(IDENTITY)
    assert r["uid"] == 65534 and r["gid"] == 65534 and r["groups"] == []
    assert set(r["caps"]) == {"0000000000000000"}
    assert r["nnp"] == ["1"]
    assert set(r["env"]) <= {"PATH", "LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING", "NODE_OPTIONS", "HOME",
                              "TMPDIR"}


# ── cannot read secrets, the database or the spool ──────────────────────────

SECRETS = """
import json, os
def tries(path):
    try:
        return ("listed", sorted(os.listdir(path))[:3]) if os.path.isdir(path) else ("read", open(path).read()[:20])
    except Exception as e:
        return ("refused", type(e).__name__)
paths = ['/data', '/data/tubematic.db', '/jobs', '/run/secrets', '/run/secrets/mcp_token', '/logs', '/backups',
         '/spool/req', '/spool/done', '/spool/heartbeat', '/root', '/var/run/docker.sock', '/proc/1/environ',
         '/proc/1/root/spool/req', '/app/api/secrets', '/etc/shadow']
print(json.dumps({p: tries(p) for p in paths}))
"""


def test_it_cannot_reach_the_database_the_secrets_the_spool_or_pid_1(box):
    r = probe(SECRETS)
    for path, (how, what) in r.items():
        # /data, /jobs, /logs and /backups exist in the image as EMPTY folders; nothing is mounted there.
        assert how == "refused" or (how == "listed" and what == []), f"{path}: {how} {what}"


def test_the_docker_socket_does_not_exist_in_the_container(box):
    r = probe("import json, os; print(json.dumps(os.path.exists('/var/run/docker.sock')))")
    assert r is False


def test_it_cannot_signal_the_daemon(box):
    code = ("import json, os\n"
            "out = {}\n"
            "for pid in (1, 2, 3):\n"
            "    try: os.kill(pid, 9); out[pid] = 'killed'\n"
            "    except Exception as e: out[pid] = type(e).__name__\n"
            "print(json.dumps(out))")
    assert set(probe(code).values()) <= {"PermissionError", "ProcessLookupError"}
    assert not run("print(1)").get("unavailable")  # the daemon still answers


# ── no network ──────────────────────────────────────────────────────────────

NET = """
import json, socket, os
out = {"ifaces": sorted(os.listdir('/sys/class/net'))}
for name, target in (("ip", ("1.1.1.1", 53)), ("local", ("127.0.0.1", 4100))):
    s = socket.socket(); s.settimeout(2)
    try: s.connect(target); out[name] = "connected"
    except Exception as e: out[name] = type(e).__name__
try: socket.getaddrinfo("example.com", 80); out["dns"] = "resolved"
except Exception as e: out["dns"] = type(e).__name__
print(json.dumps(out))
"""


def test_python_has_no_network(box):
    r = probe(NET)
    assert r["ifaces"] == ["lo"]
    assert r["ip"] != "connected" and r["local"] != "connected" and r["dns"] != "resolved"


def test_node_has_no_network_either(box):
    code = ("const net = require('net'); const dns = require('dns');\n"
            "const out = {};\n"
            "const s = net.connect({host: '1.1.1.1', port: 53, timeout: 2000});\n"
            "s.on('connect', () => { out.ip = 'connected'; s.destroy(); });\n"
            "s.on('error', (e) => { out.ip = e.code; });\n"
            "s.on('timeout', () => { out.ip = 'timeout'; s.destroy(); });\n"
            "dns.lookup('example.com', (e, a) => { out.dns = e ? e.code : 'resolved';\n"
            "  setTimeout(() => console.log(JSON.stringify(out)), 2500); });")
    r = probe(code, "javascript", timeout=15)
    assert r["ip"] != "connected" and r["dns"] != "resolved"


# ── cannot write outside its scratch ────────────────────────────────────────

WRITES = """
import json, os
def can_write(path):
    try:
        with open(os.path.join(path, 'probe.txt'), 'w') as f: f.write('x')
        os.unlink(os.path.join(path, 'probe.txt'))
        return True
    except Exception as e:
        return type(e).__name__
print(json.dumps({p: can_write(p) for p in ['/', '/app', '/app/api', '/app/sandbox', '/app/lib', '/etc', '/usr',
                                              '/spool', '/spool/req', '/spool/done', '/var', '/root']}))
"""


def test_it_can_write_nowhere_but_its_scratch(box):
    r = probe(WRITES)
    assert all(v != True for v in r.values()), r  # noqa: E712


def test_it_cannot_overwrite_the_daemon_or_the_protocol_module(box):
    code = ("import json\n"
            "out = {}\n"
            "for p in ('/app/sandbox/daemon.py', '/app/lib/tubematic_core/sandbox_protocol.py'):\n"
            "    try: open(p, 'a').write('x'); out[p] = 'WROTE'\n"
            "    except Exception as e: out[p] = type(e).__name__\n"
            "print(json.dumps(out))")
    assert set(probe(code).values()) == {"OSError"} or all(v != "WROTE" for v in probe(code).values())


def test_a_run_leaves_nothing_behind_for_the_next_one(box):
    run("import os; os.makedirs('/tmp/stash', exist_ok=True); open('/tmp/stash/a', 'w').write('secret')\n"
        "open('/tmp/loose.txt', 'w').write('x'); open('stray.txt', 'w').write('x')")
    r = probe("import json, os; print(json.dumps({'tmp': sorted(os.listdir('/tmp')), 'cwd': sorted(os.listdir('.'))}))")
    assert "stash" not in r["tmp"] and "loose.txt" not in r["tmp"] and "stray.txt" not in r["cwd"]


def test_a_symlink_or_directory_in_out_is_not_returned(box):
    code = ("import os\n"
            "os.symlink('/etc/passwd', 'out/leak.txt'); os.symlink('/spool', 'out/spool.txt')\n"
            "os.mkdir('out/dir.txt'); open('out/ok.txt', 'w').write('fine')")
    res = docker("exec", "-i", MCP, "python3", "-c", _DRIVER.replace(
        "print(json.dumps(sc.run_snippet('/sandbox', lang, code, timeout) or {\"unavailable\": True}))",
        "rid = sc.submit('/sandbox', lang, code, timeout, [])\n"
        "res = sc.wait_for_result('/sandbox', rid, timeout)\n"
        "import os\n"
        "print(json.dumps({'files': res['files'], 'listing': sorted(os.listdir('/sandbox/done/' + rid + '/out'))}))"),
        "python", "10", input=code)
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert [f["name"] for f in out["files"]] == ["ok.txt"] and out["listing"] == ["ok.txt"]


# ── limits ──────────────────────────────────────────────────────────────────

def _still_serving():
    r = run("print('alive')")
    assert r["stdout"] == "alive\n"


def test_an_infinite_loop_is_killed_at_the_timeout(box):
    start = time.time()
    r = run("while True: pass", timeout=2)
    assert r["timed_out"] is True and time.time() - start < 20
    _still_serving()


def test_a_fork_bomb_is_contained(box):
    r = run("import os\nwhile True:\n    try: os.fork()\n    except OSError: pass", timeout=3)
    assert r["timed_out"] is True or r["signal"]
    time.sleep(1)
    _still_serving()
    procs = int(docker("exec", SANDBOX, "sh", "-c", "ls /proc | grep -c '^[0-9]'", check=False).stdout.strip() or 0)
    assert procs < 20, procs  # nothing the code started is still running


def test_a_python_memory_hog_does_not_take_the_container_down(box):
    r = run("x = bytearray(6 * 1024**3)\nprint('allocated')", timeout=10)
    assert "allocated" not in r["stdout"]
    _still_serving()
    assert json.loads(docker("inspect", SANDBOX).stdout)[0]["State"]["OOMKilled"] is False


def test_a_node_memory_hog_does_not_take_the_container_down(box):
    r = run("const a = []; while (true) a.push(new Array(1e6).fill(1));", "javascript", timeout=20)
    assert r["exit_code"] != 0
    _still_serving()
    assert json.loads(docker("inspect", SANDBOX).stdout)[0]["State"]["OOMKilled"] is False


def test_huge_output_is_cut(box):
    r = run("import sys\nwhile True: sys.stdout.write('x' * 65536)", timeout=5)
    assert r["output_truncated"] is True and len(r["stdout"]) < 10000
    _still_serving()


def test_a_huge_file_is_stopped_by_the_file_size_limit(box):
    r = run("f = open('out/big.txt', 'w')\nwhile True: f.write('x' * 1048576)", timeout=20)
    # Python ignores SIGXFSZ, so the write raises "File too large"; Node would be killed by it.
    assert r["exit_code"] != 0 or r["signal"] == 25 or r["timed_out"], r
    _still_serving()


def test_ten_thousand_files_return_at_most_eight(box):
    code = "for i in range(10000):\n    open(f'out/f{i}.txt', 'w').write('x')"
    res = docker("exec", "-i", MCP, "python3", "-c", _DRIVER.replace(
        "print(json.dumps(sc.run_snippet('/sandbox', lang, code, timeout) or {\"unavailable\": True}))",
        "rid = sc.submit('/sandbox', lang, code, timeout, [])\n"
        "res = sc.wait_for_result('/sandbox', rid, timeout)\n"
        "print(len(res['files']))"), "python", "20", input=code)
    assert int(res.stdout.strip().splitlines()[-1]) <= 8
    _still_serving()


def test_a_child_that_leaves_its_process_group_is_killed(box):
    code = ("import os, time\n"
            "if os.fork() == 0:\n"
            "    os.setsid()\n"
            "    time.sleep(120)\n"
            "else:\n"
            "    print('parent done')")
    assert run(code)["stdout"] == "parent done\n"
    time.sleep(1)
    left = docker("exec", SANDBOX, "sh", "-c",
                  "for p in /proc/[0-9]*; do awk '/^Uid:/{print $2}' $p/status 2>/dev/null; done | grep -c '^65534$'",
                  check=False).stdout.strip()
    assert (left or "0") == "0"


# ── the languages work, so the controls above mean something ────────────────

def test_python_javascript_and_typescript_run(box):
    assert run("import numpy, PIL; print(numpy.arange(3).sum())")["stdout"] == "3\n"
    assert run("console.log([1, 2, 3].reduce((a, b) => a + b))", "javascript")["stdout"] == "6\n"
    r = run("const n: number = 21; console.log(n * 2)", "typescript")
    assert r["stdout"] == "42\n", r
    r = run("const n: number = ;", "typescript")
    assert r["exit_code"] != 0 and r["stderr"]


def test_the_heartbeat_is_alive_after_all_of_it(box):
    r = docker("exec", MCP, "python3", "-c",
               "import sys; sys.path[:0]=['/app/lib']\n"
               "from tubematic_core import sandbox_protocol as P\n"
               "print(P.heartbeat_age('/sandbox') < 5)")
    assert r.stdout.strip() == "True"
