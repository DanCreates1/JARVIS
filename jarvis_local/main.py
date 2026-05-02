from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from audio.recorder import AudioRecorder, AudioRecorderError
from audio.stt import SpeechToText, SpeechToTextError
from audio.tts import TextToSpeech
from llm.ollama_client import OllamaClient, OllamaError
from memory.session_memory import SessionMemory
from tools.system_tools import ToolRegistry


APP_DIR = Path(__file__).resolve().parent
LOCK_FILE = None
DEFAULT_CONFIG = {
    "model": "qwen2.5:3b",
    "ollama_chat_url": "http://localhost:11434/api/chat",
    "ollama_tags_url": "http://localhost:11434/api/tags",
    "ollama_exe": "ollama",
    "auto_start_ollama": True,
    "whisper_model": "base.en",
    "whisper_device": "auto",
    "whisper_compute_type": "auto",
    "push_to_talk_key": "right_ctrl",
    "listening_mode": "push_to_talk",
    "wake_word": "jarvis",
    "wake_word_chunk_seconds": 3,
    "post_wake_record_seconds": 6,
    "always_on_chunk_seconds": 5,
    "always_on_min_chars": 12,
    "double_clap_enabled": False,
    "double_clap_min_gap_seconds": 0.15,
    "double_clap_max_gap_seconds": 0.9,
    "double_clap_threshold": 0.35,
    "vscode_project_path": str(APP_DIR.parent),
    "vscode_exe": "",
    "codex_app_id": "OpenAI.Codex_2p2nqsd0c76g0!App",
    "log_file": "logs/jarvis.log",
    "voice": "en_US-lessac-medium",
    "piper_exe": "piper",
    "piper_model_path": "voices/en_US-lessac-medium.onnx",
    "piper_config_path": "voices/en_US-lessac-medium.onnx.json",
    "require_tool_confirmation": True,
    "max_memory_messages": 10,
    "memory_file": "memory/session_memory.json",
    "notes_dir": "notes",
    "allowed_read_dirs": ["notes"],
    "sample_rate": 16000,
    "max_record_seconds": 30,
    "idle_sleep_seconds": 0.05,
    "enable_tray": False,
}

SYSTEM_PROMPT = """You are Jarvis, a fast local Windows 11 voice assistant.
Keep replies concise and useful because they will be spoken aloud.

You can request one safe tool when it directly helps the user's request.
Available tools:
{tool_descriptions}

If you need a tool, respond with only this JSON object:
{{"tool": "tool_name", "args": {{}}, "reason": "short reason"}}

Rules:
- Do not invent tool results.
- Do not say a tool ran until a tool result is provided.
- For normal conversation, answer normally without JSON.
- Prefer short answers unless the user asks for detail.
"""


def load_config() -> dict[str, Any]:
    config_path = APP_DIR / "config.json"
    config = DEFAULT_CONFIG.copy()
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        config.update(loaded)
    return config


def setup_logging(config: dict[str, Any]) -> None:
    log_path = resolve_app_path(config["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def resolve_app_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return APP_DIR / path


def resolve_executable(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    if path.parent != Path("."):
        return str(APP_DIR / path)
    return value


def resolve_optional_path(value: str) -> Path | None:
    if not value:
        return None
    return resolve_app_path(value)


def acquire_single_instance() -> bool:
    global LOCK_FILE
    lock_path = APP_DIR / "logs" / "jarvis.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE = lock_path.open("a+b")

    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(LOCK_FILE.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    try:
        import fcntl

        fcntl.flock(LOCK_FILE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class JarvisApp:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.log = logging.getLogger("jarvis")
        self.stop_event = threading.Event()
        self.listening_enabled = threading.Event()
        self.listening_enabled.set()

        self.tools = ToolRegistry(
            app_dir=APP_DIR,
            notes_dir=resolve_app_path(config["notes_dir"]),
            allowed_read_dirs=[
                resolve_app_path(path) for path in config.get("allowed_read_dirs", [])
            ],
            vscode_project_path=resolve_app_path(config["vscode_project_path"]),
            vscode_exe=resolve_optional_path(str(config.get("vscode_exe", ""))),
            codex_app_id=str(config.get("codex_app_id", "")),
        )
        self.memory = SessionMemory(
            path=resolve_app_path(config["memory_file"]),
            max_messages=int(config["max_memory_messages"]),
        )
        self.llm = OllamaClient(
            model=config["model"],
            chat_url=config["ollama_chat_url"],
            tags_url=config["ollama_tags_url"],
        )
        self.tts = TextToSpeech(
            piper_exe=resolve_executable(config["piper_exe"]),
            model_path=resolve_app_path(config["piper_model_path"]),
            config_path=resolve_app_path(config["piper_config_path"]),
            voice_name=config["voice"],
        )
        self.recorder = AudioRecorder(
            sample_rate=int(config["sample_rate"]),
            max_record_seconds=float(config["max_record_seconds"]),
            idle_sleep_seconds=float(config["idle_sleep_seconds"]),
        )
        self.stt = SpeechToText(
            model_name=config["whisper_model"],
            device=config["whisper_device"],
            compute_type=config["whisper_compute_type"],
        )
        self.system_prompt = SYSTEM_PROMPT.format(
            tool_descriptions=self.tools.prompt_description()
        )

    def run(self) -> None:
        self.log.info("Jarvis starting")
        self.memory.load()
        self._install_shutdown_handlers()
        self._preflight()
        self._start_tray_if_enabled()
        self.tts.speak("Jarvis is ready.")

        mode = str(self.config.get("listening_mode", "push_to_talk")).lower()
        if mode == "always_on":
            self._always_on_loop()
        elif mode == "wake_word":
            self._wake_word_loop()
        else:
            self._push_to_talk_loop()

    def _preflight(self) -> None:
        try:
            self.recorder.check_microphone()
        except AudioRecorderError as exc:
            self.log.error("Microphone error: %s", exc)
            self.tts.speak("I cannot find a working microphone. Check the log.")

        try:
            models = self.llm.list_models()
            if self.config["model"] not in models:
                self.log.warning(
                    "Ollama model %s was not found. Installed models: %s",
                    self.config["model"],
                    ", ".join(models) or "(none)",
                )
        except OllamaError as exc:
            if self.config.get("auto_start_ollama", True):
                self.log.warning("Ollama not ready, trying to start it: %s", exc)
                self._start_ollama()
                time.sleep(5)
                try:
                    self.llm.list_models()
                    self.log.info("Ollama started successfully")
                    return
                except OllamaError as retry_exc:
                    exc = retry_exc
            self.log.error("Ollama preflight failed: %s", exc)
            self.tts.speak("Ollama is not ready. Start Ollama and check the log.")

    def _start_ollama(self) -> None:
        command = [resolve_executable(str(self.config.get("ollama_exe", "ollama"))), "serve"]
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            self.log.warning("Could not start Ollama automatically: %s", exc)

    def _push_to_talk_loop(self) -> None:
        key = self._keyboard_key()
        self.log.info("Listening in push-to-talk mode on key: %s", key)
        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.2)
                continue

            try:
                audio_path = self.recorder.wait_for_push_to_talk(
                    key=key,
                    stop_event=self.stop_event,
                )
            except AudioRecorderError as exc:
                self.log.error("Recording failed: %s", exc)
                self.tts.speak("Recording failed. Check the log.")
                time.sleep(1.0)
                continue

            if audio_path is None:
                continue
            self._handle_audio(audio_path)

    def _wake_word_loop(self) -> None:
        wake_word = str(self.config.get("wake_word", "jarvis")).lower()
        chunk_seconds = float(self.config.get("wake_word_chunk_seconds", 3))
        self.log.info("Listening in lightweight wake-word mode: %s", wake_word)
        self.tts.speak("Wake word mode is on.")

        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.5)
                continue
            audio_path = None
            try:
                audio_path = self.recorder.record_for(
                    seconds=chunk_seconds,
                    stop_event=self.stop_event,
                )
                if audio_path is None:
                    continue
                if self._handle_double_clap_if_detected(audio_path):
                    continue
                text = self.stt.transcribe(audio_path).strip()
            except (AudioRecorderError, SpeechToTextError) as exc:
                self.log.error("Wake-word pass failed: %s", exc)
                time.sleep(1.0)
                continue
            finally:
                if audio_path is not None:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            lower = text.lower()
            if wake_word not in lower:
                continue
            request = lower.split(wake_word, 1)[1].strip(" ,.")
            if not request:
                self.tts.speak("Yes?")
                request_audio = self.recorder.record_for(
                    seconds=float(self.config.get("post_wake_record_seconds", 6)),
                    stop_event=self.stop_event,
                )
                if request_audio is None:
                    continue
                self._handle_audio(request_audio)
            else:
                self._handle_text(request)

    def _always_on_loop(self) -> None:
        chunk_seconds = float(self.config.get("always_on_chunk_seconds", 5))
        min_chars = int(self.config.get("always_on_min_chars", 12))
        self.log.info("Listening in always-on hands-free mode")
        self.tts.speak("Hands-free mode is on.")

        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.5)
                continue
            audio_path = None
            try:
                audio_path = self.recorder.record_for(
                    seconds=chunk_seconds,
                    stop_event=self.stop_event,
                )
                if audio_path is None:
                    continue
                if self._handle_double_clap_if_detected(audio_path):
                    continue
                text = self.stt.transcribe(audio_path).strip()
            except (AudioRecorderError, SpeechToTextError) as exc:
                self.log.error("Always-on listening pass failed: %s", exc)
                time.sleep(1.0)
                continue
            finally:
                if audio_path is not None:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            if not text:
                continue
            if len(text) < min_chars:
                self.log.info("Ignored short always-on transcript: %s", text)
                continue
            if self._looks_like_background_noise(text):
                self.log.info("Ignored likely background transcript: %s", text)
                continue
            self.log.info("Always-on user said: %s", text)
            self._handle_text(text)

    def _looks_like_background_noise(self, text: str) -> bool:
        cleaned = text.strip().lower().strip(".!?")
        ignored = {
            "thank you",
            "thanks for watching",
            "amen",
            "okay",
            "good",
            "you",
        }
        return cleaned in ignored

    def _handle_double_clap_if_detected(self, audio_path: Path) -> bool:
        if not self.config.get("double_clap_enabled", False):
            return False
        try:
            detected = self.recorder.detect_double_clap(
                audio_path=audio_path,
                threshold=float(self.config.get("double_clap_threshold", 0.35)),
                min_gap_seconds=float(self.config.get("double_clap_min_gap_seconds", 0.15)),
                max_gap_seconds=float(self.config.get("double_clap_max_gap_seconds", 0.9)),
            )
        except AudioRecorderError as exc:
            self.log.warning("Double-clap detection failed: %s", exc)
            return False
        if not detected:
            return False
        self.log.info("Double clap detected")
        self.tts.speak("Opening Codex and VS Code.")
        result = self.tools.run("open_workspace", {})
        self.log.info("Double-clap action result: %s", result.message)
        return True

    def _handle_audio(self, audio_path: Path) -> None:
        try:
            text = self.stt.transcribe(audio_path).strip()
        except SpeechToTextError as exc:
            self.log.error("Transcription failed: %s", exc)
            self.tts.speak("I could not transcribe that. Check the log.")
            return
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass

        if not text:
            self.log.info("Ignored empty transcript")
            return
        self.log.info("User said: %s", text)
        self._handle_text(text)

    def _handle_text(self, user_text: str) -> None:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.memory.messages)
        messages.append({"role": "user", "content": user_text})

        try:
            assistant_text = self.llm.chat(messages)
        except OllamaError as exc:
            self.log.error("Ollama chat failed: %s", exc)
            self.tts.speak(str(exc))
            return

        tool_request = self.tools.parse_tool_request(assistant_text)
        if tool_request is None:
            self.memory.add("user", user_text)
            self.memory.add("assistant", assistant_text)
            self.tts.speak(assistant_text)
            self.memory.save()
            return

        final_text = self._run_tool_round(user_text, messages, assistant_text, tool_request)
        self.memory.add("user", user_text)
        self.memory.add("assistant", final_text)
        self.memory.save()
        self.tts.speak(final_text)

    def _run_tool_round(
        self,
        user_text: str,
        messages: list[dict[str, str]],
        assistant_text: str,
        tool_request: dict[str, Any],
    ) -> str:
        tool_name = str(tool_request.get("tool", ""))
        args = tool_request.get("args") or {}
        reason = str(tool_request.get("reason", ""))
        self.log.info("LLM requested tool %s with args %s", tool_name, args)

        if self.tools.requires_confirmation(tool_name) and self.config.get(
            "require_tool_confirmation", True
        ):
            if not self._confirm_tool(tool_name, args, reason):
                return f"Cancelled {tool_name}."

        result = self.tools.run(tool_name, args)
        self.log.info("Tool result: %s", result.message)

        followup = list(messages)
        followup.append({"role": "assistant", "content": assistant_text})
        followup.append(
            {
                "role": "user",
                "content": (
                    "Tool result for the original request:\n"
                    f"Tool: {tool_name}\n"
                    f"Success: {result.success}\n"
                    f"Result: {result.message}\n\n"
                    "Now reply to the user with a short spoken response."
                ),
            }
        )
        try:
            return self.llm.chat(followup)
        except OllamaError as exc:
            self.log.error("Ollama follow-up failed: %s", exc)
            return result.message

    def _confirm_tool(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        if not self.tts.available:
            self.log.warning("Cannot confirm tool because TTS is unavailable")
            return False

        key = self._keyboard_key()
        args_preview = self.tools.describe_args(tool_name, args)
        prompt = (
            f"I need confirmation to run {tool_name}. "
            f"{reason or args_preview} "
        )
        if str(self.config.get("listening_mode", "")).lower() == "wake_word":
            prompt += "Say yes now to confirm."
        else:
            prompt += f"Hold {key} and say yes to confirm."
        self.tts.speak(prompt)

        try:
            audio_path = None
            if str(self.config.get("listening_mode", "")).lower() == "wake_word":
                audio_path = self.recorder.record_for(
                    seconds=4,
                    stop_event=self.stop_event,
                )
            else:
                audio_path = self.recorder.wait_for_push_to_talk(
                    key=key,
                    stop_event=self.stop_event,
                    timeout_seconds=20,
                )
            if audio_path is None:
                self.log.info("Tool confirmation timed out")
                return False
            text = self.stt.transcribe(audio_path).strip().lower()
        except (AudioRecorderError, SpeechToTextError, OSError) as exc:
            self.log.error("Confirmation failed: %s", exc)
            return False
        finally:
            if audio_path is not None:
                try:
                    audio_path.unlink(missing_ok=True)
                except OSError:
                    pass

        self.log.info("Confirmation transcript: %s", text)
        yes_phrases = ("yes", "confirm", "confirmed", "do it", "proceed", "sure", "okay")
        no_phrases = ("no", "cancel", "stop", "do not", "don't")
        if any(phrase in text for phrase in no_phrases):
            return False
        return any(phrase in text for phrase in yes_phrases)

    def _keyboard_key(self) -> str:
        return str(self.config["push_to_talk_key"]).replace("_", " ")

    def _start_tray_if_enabled(self) -> None:
        if not self.config.get("enable_tray", False):
            return
        try:
            from tray_icon import start_tray

            start_tray(
                listening_enabled=self.listening_enabled,
                stop_event=self.stop_event,
                logger=logging.getLogger("jarvis.tray"),
            )
            self.log.info("Tray icon enabled")
        except Exception as exc:
            self.log.warning("Tray icon unavailable: %s", exc)

    def _install_shutdown_handlers(self) -> None:
        def stop(*_: object) -> None:
            self.log.info("Shutdown requested")
            self.stop_event.set()
            self.memory.save()

        atexit.register(stop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, stop)
            except ValueError:
                pass


def main() -> int:
    config = load_config()
    setup_logging(config)
    for relative in ("logs", "memory", "notes", "voices"):
        (APP_DIR / relative).mkdir(parents=True, exist_ok=True)

    try:
        if not acquire_single_instance():
            logging.getLogger("jarvis").info("Another Jarvis instance is already running")
            return 0
        app = JarvisApp(config)
        app.run()
        return 0
    except Exception:
        logging.exception("Fatal Jarvis error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
