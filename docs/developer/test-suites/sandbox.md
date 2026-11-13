# `sandbox/tests`

Covers the code sandbox: the daemon in `sandbox/daemon.py` and the container that runs it
([`tubematic-sandbox`](../16-infrastructure.md#tubematic-sandbox)). The MCP side is in
[`test_run_code.py`](mcp.md#test_run_codepy).

```bash
python -m pytest sandbox/tests
TUBEMATIC_SANDBOX_IT_IMAGE=<image> python -m pytest sandbox/tests/test_container.py
```

## `test_daemon.py`

Covers the run loop, run as the current user with no container. It pins the protocol and the limits.

- A run returns stdout, its exit code and its stderr. A failing run reports both. The request folder
  is consumed and the work folder is empty afterwards.
- An infinite loop is killed at the timeout, and so is a child it started. Huge output is cut and
  flagged, and the environment the code sees holds none of the daemon's variables.
- Inputs appear in `./in`, and only regular files with an allowed name and extension come back from
  `./out`: a symlink, a directory, a hidden name, a bad extension and anything past the count and size
  limits are dropped.
- A request that fails validation (language, empty or large code, timeout, input names) and one that
  cannot be read become an error result. A crash inside a run does the same and the loop goes on.
- Stale results and half-written temporaries are swept, and the spool folders are private. What a
  uid leaves in the shared tmpfs is deleted.
- JavaScript and TypeScript run when Node and esbuild are installed on the machine.

CI does not run `test_container.py`: it would have to build the whole backend image. The compose flags are
pinned statically in `onboard/tests/test_compose_topology.py`, which CI does run, and a branch that changes
the sandbox runs this file by hand and in the live test before it merges.

Trap: the suite runs as an ordinary user, so the process limit (`RLIMIT_NPROC`, which counts every
process of the uid) is off. It only means something in the container, where the code has a uid of its
own.

## `test_container.py`

The negative controls. It starts two throwaway containers: the sandbox, with every flag read from the
`tubematic-sandbox` service in `docker-compose.yml`, and a second one standing for the MCP server (root,
default capabilities, the same spool). It submits hostile code through `mcp/sandbox_client.py` as MCP
does and removes both containers by exact name.

The suite needs an image that holds `/app/sandbox/daemon.py`, `tubematic_core` and
`/app/mcp/sandbox_client.py`: the backend image built from the branch, or a thin layer over a test
image that copies those files in. It skips when `TUBEMATIC_SANDBOX_IT_IMAGE` is not set. It uses no
GPU, no network and no volume but a temporary spool.

- The container has no network, a read-only root, all capabilities dropped, `no-new-privileges`, one
  mount, no environment key and limits. The code runs as uid 65534 with no capabilities and a scrubbed
  environment.
- The code cannot read or list the database, the secrets, the logs, the backups, the spool, a
  process's environment or another process's root, and the Docker socket does not exist. It cannot
  signal the daemon.
- Python and Node cannot connect to an address, a loopback port or resolve a name. The only network
  interface is `lo`.
- The code can write nowhere but its scratch: not the image, `/app`, the spool or the filesystem root,
  and it cannot overwrite the daemon or the protocol module. What it leaves in `/tmp` or the work
  folder is gone for the next run. A symlink or a directory in `./out` is not returned.
- An infinite loop, a fork bomb, a Python and a Node memory hog, an endless output, an endless file
  and ten thousand files are each contained. The daemon answers the next request, the container is not
  killed for memory, and no process or zombie of the code is left.
- Python (with numpy and Pillow), JavaScript and TypeScript run, and a TypeScript syntax error is
  reported.

Trap: the daemon is PID 1, so a process the code leaves behind is adopted by it and stays a zombie
until the daemon waits for it. A fork bomb filled the container's process limit before the daemon
reaped them, and every later run failed. `test_a_fork_bomb_is_contained` counts the processes after
the run.
