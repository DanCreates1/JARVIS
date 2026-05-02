from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolResult:
    success: bool
    message: str


@dataclass
class ToolSpec:
    name: str
    description: str
    args: str
    requires_confirmation: bool
    handler: Callable[[dict[str, Any]], ToolResult]


class ToolRegistry:
    def __init__(
        self,
        app_dir: Path,
        notes_dir: Path,
        allowed_read_dirs: list[Path],
        vscode_project_path: Path | None = None,
        vscode_exe: Path | None = None,
        codex_app_id: str = "",
    ) -> None:
        self.app_dir = app_dir.resolve()
        self.notes_dir = notes_dir.resolve()
        self.allowed_read_dirs = [path.resolve() for path in allowed_read_dirs]
        self.vscode_project_path = (
            vscode_project_path.resolve() if vscode_project_path else self.app_dir.parent
        )
        self.vscode_exe = vscode_exe.resolve() if vscode_exe else None
        self.codex_app_id = codex_app_id
        if self.notes_dir not in self.allowed_read_dirs:
            self.allowed_read_dirs.append(self.notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger("jarvis.tools")
        self._tools = self._build_tools()

    def prompt_description(self) -> str:
        lines = []
        for spec in self._tools.values():
            lines.append(f"- {spec.name}: {spec.description} Args: {spec.args}")
        return "\n".join(lines)

    def parse_tool_request(self, text: str) -> dict[str, Any] | None:
        text = self._strip_code_fence(text.strip())
        if not text.startswith("{"):
            first = text.find("{")
            if first == -1:
                return None
            text = text[first:]
        decoder = json.JSONDecoder()
        try:
            parsed, _idx = decoder.raw_decode(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict) or "tool" not in parsed:
            return None
        tool_name = str(parsed.get("tool"))
        if tool_name not in self._tools:
            self.log.warning("LLM requested unknown tool: %s", tool_name)
            return None
        args = parsed.get("args")
        if args is None:
            parsed["args"] = {}
        elif not isinstance(args, dict):
            parsed["args"] = {}
        return parsed

    def run(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        spec = self._tools.get(tool_name)
        if spec is None:
            return ToolResult(False, f"Unknown tool: {tool_name}")
        try:
            return spec.handler(args)
        except Exception as exc:
            self.log.exception("Tool %s failed", tool_name)
            return ToolResult(False, f"{tool_name} failed: {exc}")

    def requires_confirmation(self, tool_name: str) -> bool:
        spec = self._tools.get(tool_name)
        return True if spec is None else spec.requires_confirmation

    def describe_args(self, tool_name: str, args: dict[str, Any]) -> str:
        if not args:
            return ""
        safe = json.dumps(args, ensure_ascii=True)
        if len(safe) > 160:
            safe = safe[:157] + "..."
        return f"Arguments: {safe}"

    def _build_tools(self) -> dict[str, ToolSpec]:
        specs = [
            ToolSpec(
                name="open_notepad",
                description="Open Windows Notepad.",
                args="{}",
                requires_confirmation=True,
                handler=self._open_notepad,
            ),
            ToolSpec(
                name="open_chrome",
                description="Open Google Chrome if it is installed.",
                args='{"url": "optional URL to open"}',
                requires_confirmation=True,
                handler=self._open_chrome,
            ),
            ToolSpec(
                name="get_time",
                description="Return the current local date and time.",
                args="{}",
                requires_confirmation=False,
                handler=self._get_time,
            ),
            ToolSpec(
                name="create_note",
                description="Save a text note under the local notes folder.",
                args='{"title": "short file title", "content": "note text"}',
                requires_confirmation=True,
                handler=self._create_note,
            ),
            ToolSpec(
                name="read_text_file",
                description="Read a small text file from an allowed local folder.",
                args='{"path": "path under notes/ or another configured allowed folder"}',
                requires_confirmation=True,
                handler=self._read_text_file,
            ),
            ToolSpec(
                name="open_codex",
                description="Open the Codex Windows app.",
                args="{}",
                requires_confirmation=True,
                handler=self._open_codex,
            ),
            ToolSpec(
                name="open_vscode_project",
                description="Open the configured project folder in Visual Studio Code.",
                args='{"path": "optional project folder"}',
                requires_confirmation=True,
                handler=self._open_vscode_project,
            ),
            ToolSpec(
                name="open_workspace",
                description="Open Codex and the configured project folder in Visual Studio Code.",
                args="{}",
                requires_confirmation=True,
                handler=self._open_workspace,
            ),
        ]
        return {spec.name: spec for spec in specs}

    def _open_notepad(self, args: dict[str, Any]) -> ToolResult:
        subprocess.Popen(
            ["notepad.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        return ToolResult(True, "Opened Notepad.")

    def _open_chrome(self, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url") or "").strip()
        command = [self._chrome_path()]
        if url:
            command.append(url)
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        return ToolResult(True, "Opened Chrome." if not url else f"Opened Chrome to {url}.")

    def _get_time(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(True, time.strftime("%A, %B %d, %Y at %I:%M %p"))

    def _create_note(self, args: dict[str, Any]) -> ToolResult:
        title = str(args.get("title") or "note")
        content = str(args.get("content") or "").strip()
        if not content:
            return ToolResult(False, "No note content was provided.")

        filename = self._safe_filename(title)
        path = self.notes_dir / f"{filename}.txt"
        counter = 2
        while path.exists():
            path = self.notes_dir / f"{filename}_{counter}.txt"
            counter += 1
        path.write_text(content + "\n", encoding="utf-8")
        return ToolResult(True, f"Saved note to {path}.")

    def _read_text_file(self, args: dict[str, Any]) -> ToolResult:
        raw_path = str(args.get("path") or "").strip()
        if not raw_path:
            return ToolResult(False, "No file path was provided.")
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.app_dir / path
        path = path.resolve()

        if not self._is_allowed_read_path(path):
            return ToolResult(
                False,
                f"Refused to read {path}. Add its folder to allowed_read_dirs in config.json.",
            )
        if not path.exists() or not path.is_file():
            return ToolResult(False, f"File not found: {path}")
        if path.suffix.lower() not in {".txt", ".md", ".json", ".log", ".csv"}:
            return ToolResult(False, "Only small text-like files are allowed.")
        if path.stat().st_size > 50_000:
            return ToolResult(False, "File is larger than the 50 KB safety limit.")
        return ToolResult(True, path.read_text(encoding="utf-8", errors="replace"))

    def _open_codex(self, args: dict[str, Any]) -> ToolResult:
        if not self.codex_app_id:
            return ToolResult(False, "No Codex app ID is configured.")
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{self.codex_app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        return ToolResult(True, "Opened Codex.")

    def _open_vscode_project(self, args: dict[str, Any]) -> ToolResult:
        raw_path = str(args.get("path") or "").strip()
        project_path = Path(raw_path) if raw_path else self.vscode_project_path
        if not project_path.is_absolute():
            project_path = self.app_dir / project_path
        project_path = project_path.resolve()
        if not project_path.exists() or not project_path.is_dir():
            return ToolResult(False, f"VS Code project folder not found: {project_path}")

        vscode = self._vscode_path()
        subprocess.Popen(
            [vscode, str(project_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=self._creation_flags(),
        )
        return ToolResult(True, f"Opened VS Code at {project_path}.")

    def _open_workspace(self, args: dict[str, Any]) -> ToolResult:
        codex = self._open_codex({})
        vscode = self._open_vscode_project({})
        success = codex.success and vscode.success
        return ToolResult(success, f"{codex.message} {vscode.message}")

    def _is_allowed_read_path(self, path: Path) -> bool:
        for allowed in self.allowed_read_dirs:
            try:
                path.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def _safe_filename(self, title: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "", title).strip().replace(" ", "_")
        cleaned = cleaned.strip("._")
        return cleaned[:60] or "note"

    def _chrome_path(self) -> str:
        candidates = [
            os.environ.get("ProgramFiles", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("ProgramFiles(x86)", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("LocalAppData", "") + r"\Google\Chrome\Application\chrome.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return "chrome.exe"

    def _vscode_path(self) -> str:
        if self.vscode_exe and self.vscode_exe.exists():
            return str(self.vscode_exe)
        candidates = [
            os.environ.get("LocalAppData", "") + r"\Programs\Microsoft VS Code\Code.exe",
            os.environ.get("ProgramFiles", "") + r"\Microsoft VS Code\Code.exe",
            os.environ.get("ProgramFiles(x86)", "") + r"\Microsoft VS Code\Code.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return "code"

    def _strip_code_fence(self, text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
        return text

    def _creation_flags(self) -> int:
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0
