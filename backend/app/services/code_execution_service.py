"""Code execution tool: run Python inside an isolated Docker container.

Lets subagents *verify* their work (run the code they wrote, compute
statistics) instead of guessing. Sandbox properties: no network, memory/CPU/
process limits, read-only filesystem, all capabilities dropped, code delivered
via stdin (no volume mounts). Best-effort by design: if Docker is unavailable
the tool silently disables itself and the pipeline keeps running.

Known residual risk: if the backend process dies between spawning the docker
CLI and the timeout cleanup, a container may briefly outlive us — acceptable
because it has no network, a hard memory cap, and ``--rm`` removes it on exit.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.core.constants import (
    CODE_EXECUTION_OUTPUT_MAX_CHARS,
    CODE_EXECUTION_RESULT_CLOSE,
    CODE_EXECUTION_RESULT_OPEN,
)

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 5.0
_availability: bool | None = None
_availability_lock = asyncio.Lock()


@dataclass(slots=True)
class ExecutionResult:
    """Outcome of one sandboxed run."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    timed_out: bool = False


async def is_available() -> bool:
    """True if a Docker daemon answers. Probed once per process (cached)."""
    global _availability
    if _availability is not None:
        return _availability
    async with _availability_lock:
        if _availability is not None:
            return _availability
        _availability = await _probe_docker()
        if not _availability:
            logger.info("Docker unavailable; code_execution tool disabled")
    return _availability


async def _probe_docker() -> bool:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "version",
            "--format",
            "{{.Server.Version}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return False
    try:
        await asyncio.wait_for(process.communicate(), timeout=_PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        return False
    return process.returncode == 0


async def run_python(code: str) -> ExecutionResult:
    """Execute Python source in the sandbox container. Never raises."""
    container = f"maestro-exec-{uuid.uuid4().hex[:12]}"
    command = (
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        container,
        "--network",
        "none",
        "--memory",
        settings.code_execution_memory_limit,
        "--cpus",
        settings.code_execution_cpus,
        "--pids-limit",
        "128",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        settings.code_execution_image,
        "python",
        "-I",
        "-",
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return ExecutionResult(stderr=f"could not start sandbox: {exc}")

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=code.encode()),
            timeout=settings.code_execution_timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        # Killing the docker CLI does not kill the container — kill it by name.
        await _kill_container(container)
        return ExecutionResult(timed_out=True)

    return ExecutionResult(
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        exit_code=process.returncode if process.returncode is not None else -1,
    )


async def _kill_container(name: str) -> None:
    """Best-effort ``docker kill`` for a timed-out run."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "kill",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=_PROBE_TIMEOUT_SECONDS)
    except (OSError, TimeoutError):
        logger.warning("Could not kill sandbox container %s", name)


def format_execution_block(result: ExecutionResult) -> str:
    """Render an execution result as a delimited block for the LLM."""
    if result.timed_out:
        body = (
            "Execution timed out after "
            f"{settings.code_execution_timeout_seconds}s and was terminated."
        )
    else:
        parts = [f"Exit code: {result.exit_code}"]
        stdout = result.stdout.strip()[:CODE_EXECUTION_OUTPUT_MAX_CHARS]
        stderr = result.stderr.strip()[:CODE_EXECUTION_OUTPUT_MAX_CHARS]
        parts.append(f"stdout:\n{stdout}" if stdout else "stdout: (empty)")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        body = "\n".join(parts)
    return "\n".join([CODE_EXECUTION_RESULT_OPEN, body, CODE_EXECUTION_RESULT_CLOSE])
