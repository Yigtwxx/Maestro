"""Docker sandbox service: probe caching, run paths, timeout kill (no docker)."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.core.constants import CODE_EXECUTION_RESULT_OPEN
from app.services import code_execution_service
from app.services.code_execution_service import ExecutionResult


class FakeProcess:
    """Stand-in for an asyncio subprocess."""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        hang: bool = False,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._hang = hang
        self.killed = False

    async def communicate(self, input: bytes | None = None):
        if self._hang:
            await asyncio.sleep(3600)
        return self._stdout, self._stderr

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


@pytest.fixture(autouse=True)
def _reset_probe_cache(monkeypatch):
    monkeypatch.setattr(code_execution_service, "_availability", None)


def _patch_subprocess(monkeypatch, factory):
    """Replace create_subprocess_exec inside the service module."""
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*args, **kwargs):
        commands.append(args)
        return factory(args)

    monkeypatch.setattr(
        code_execution_service.asyncio, "create_subprocess_exec", fake_exec
    )
    return commands


async def test_is_available_true_and_cached(monkeypatch):
    commands = _patch_subprocess(
        monkeypatch, lambda args: FakeProcess(stdout=b"27.0.1")
    )
    assert await code_execution_service.is_available() is True
    assert await code_execution_service.is_available() is True
    assert len(commands) == 1, f"Probe must be cached, ran {len(commands)} times"


async def test_is_available_false_when_docker_missing(monkeypatch):
    async def fake_exec(*args, **kwargs):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(
        code_execution_service.asyncio, "create_subprocess_exec", fake_exec
    )
    assert await code_execution_service.is_available() is False


async def test_run_python_returns_stdout_and_exit_code(monkeypatch):
    commands = _patch_subprocess(
        monkeypatch, lambda args: FakeProcess(stdout=b"4\n", returncode=0)
    )
    result = await code_execution_service.run_python("print(2 + 2)")
    assert result.stdout == "4\n", result
    assert result.exit_code == 0, result
    assert result.timed_out is False, result
    command = commands[0]
    assert "--network" in command and "none" in command, (
        f"Sandbox must disable networking: {command}"
    )
    assert "--read-only" in command, f"Sandbox must be read-only: {command}"


async def test_run_python_timeout_kills_container(monkeypatch):
    processes: list[FakeProcess] = []

    def factory(args: tuple[str, ...]) -> FakeProcess:
        process = FakeProcess(hang="run" in args)
        processes.append(process)
        return process

    commands = _patch_subprocess(monkeypatch, factory)
    monkeypatch.setattr(settings, "code_execution_timeout_seconds", 0)

    result = await code_execution_service.run_python("while True: pass")
    assert result.timed_out is True, result
    assert processes[0].killed is True, "docker CLI process must be killed"
    kill_commands = [c for c in commands if c[:2] == ("docker", "kill")]
    assert len(kill_commands) == 1, f"Expected docker kill, got {commands}"


async def test_run_python_docker_start_failure_never_raises(monkeypatch):
    async def fake_exec(*args, **kwargs):
        raise OSError("cannot spawn")

    monkeypatch.setattr(
        code_execution_service.asyncio, "create_subprocess_exec", fake_exec
    )
    result = await code_execution_service.run_python("print(1)")
    assert "could not start sandbox" in result.stderr, result


def test_format_execution_block_includes_stdout_and_exit_code():
    block = code_execution_service.format_execution_block(
        ExecutionResult(stdout="hello", stderr="", exit_code=0)
    )
    assert CODE_EXECUTION_RESULT_OPEN in block, block
    assert "Exit code: 0" in block, block
    assert "hello" in block, block


def test_format_execution_block_reports_timeout():
    block = code_execution_service.format_execution_block(
        ExecutionResult(timed_out=True)
    )
    assert "timed out" in block, block
