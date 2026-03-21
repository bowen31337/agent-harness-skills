"""Plugin gate configuration and runner."""
from __future__ import annotations
import os
import re
import subprocess
import time
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, field_validator
from harness_skills.models.base import GateResult, Status, Violation


class PluginGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate_id: str
    gate_name: str
    command: str
    timeout_seconds: int = 60
    fail_on_error: bool = True
    severity: Literal["error", "warning", "info"] = "error"
    env: dict[str, str] = {}

    @field_validator("gate_id")
    @classmethod
    def validate_gate_id(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"gate_id must match ^[a-z][a-z0-9_]*$, got " + repr(v))
        return v

    @field_validator("gate_name")
    @classmethod
    def validate_gate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("gate_name must not be empty")
        return stripped

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("command must not be empty")
        return stripped

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if not (1 <= v <= 3600):
            raise ValueError("timeout_seconds must be between 1 and 3600")
        return v


class PluginGateRunner:
    def __init__(self, config: PluginGateConfig) -> None:
        self.config = config

    def run(self) -> GateResult:
        cfg = self.config
        start = time.monotonic()
        expanded_env = {k: os.path.expandvars(v) for k, v in cfg.env.items()}
        merged_env = {**os.environ, **expanded_env}
        try:
            proc = subprocess.run(
                cfg.command, shell=True, capture_output=True, text=True,
                timeout=cfg.timeout_seconds, env=merged_env,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if proc.returncode == 0:
                return GateResult(gate_id=cfg.gate_id, gate_name=cfg.gate_name,
                                  status=Status.PASSED, duration_ms=elapsed_ms)
            output = (proc.stdout + proc.stderr)[:500]
            status = Status.FAILED if cfg.fail_on_error else Status.WARNING
            return GateResult(
                gate_id=cfg.gate_id, gate_name=cfg.gate_name,
                status=status, duration_ms=elapsed_ms,
                violations=[Violation(rule_id="plugin/exit_nonzero", severity=cfg.severity,
                                      message=f"Command exited with code {proc.returncode}: {output}",
                                      suggestion=f"Check the output of: {cfg.command}")],
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status = Status.FAILED if cfg.fail_on_error else Status.WARNING
            return GateResult(
                gate_id=cfg.gate_id, gate_name=cfg.gate_name,
                status=status, duration_ms=elapsed_ms,
                violations=[Violation(rule_id="plugin/timeout", severity=cfg.severity,
                                      message=f"Command timed out after {cfg.timeout_seconds}s: {cfg.command}",
                                      suggestion="Increase timeout_seconds or optimize the command.")],
            )
