from __future__ import annotations

import atexit
import json
import logging
import os
import queue
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
    "ollama_keep_alive": "30m",
    "ollama_temperature": 0.2,
    "ollama_num_ctx": 2048,
    "ollama_num_predict": 96,
    "ollama_top_p": 0.9,
    "ollama_warmup": True,
    "whisper_model": "base.en",
    "whisper_device": "auto",
    "whisper_compute_type": "auto",
    "stt_warmup": True,
    "push_to_talk_key": "right_ctrl",
    "listening_mode": "push_to_talk",
    "wake_word": "jarvis",
    "wake_word_required": True,
    "wake_word_chunk_seconds": 3,
    "post_wake_record_seconds": 6,
    "always_on_chunk_seconds": 5,
    "always_on_use_vad": True,
    "vad_speech_threshold": 0.018,
    "vad_silence_seconds": 0.65,
    "vad_min_record_seconds": 0.9,
    "vad_start_timeout_seconds": 10,
    "force_listen_start_timeout_seconds": 8,
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
    "enable_status_gui": False,
    "status_gui_fullscreen": False,
}

SYSTEM_PROMPT = """You are Jarvis, a fast local Windows 11 voice assistant.
Your style is JARVIS-inspired: composed, precise, lightly witty, and efficient.
You are not the Iron Man character or that exact voice. Do not claim to be.
Keep replies short because they will be spoken aloud. Use one or two sentences by default.

You can request one safe tool when it directly helps the user's request.
Available tools:
{tool_descriptions}

If you need a tool, respond with only this JSON object:
{{"tool": "tool_name", "args": {{}}, "reason": "short reason"}}

Rules:
- Do not invent tool results.
- Do not say a tool ran until a tool result is provided.
- Do not read code, stack traces, logs, or long file contents aloud unless the user explicitly asks you to read them verbatim.
- If the user asks about code, summarize the important point briefly instead of reciting code.
- For normal conversation, answer normally without JSON.
- Prefer short, polished answers unless the user asks for detail.
- Avoid filler like "Sure" when a direct answer is better.
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
        self.force_command_event = threading.Event()
        self.typed_command_queue: queue.Queue[str] = queue.Queue()
        self.status_gui = None

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
            keep_alive=config.get("ollama_keep_alive", "30m"),
            options={
                "temperature": float(config.get("ollama_temperature", 0.2)),
                "num_ctx": int(config.get("ollama_num_ctx", 2048)),
                "num_predict": int(config.get("ollama_num_predict", 96)),
                "top_p": float(config.get("ollama_top_p", 0.9)),
            },
        )
        self.tts = TextToSpeech(
            piper_exe=resolve_executable(config["piper_exe"]),
            model_path=resolve_app_path(config["piper_model_path"]),
            config_path=resolve_app_path(config["piper_config_path"]),
            voice_name=config["voice"],
            length_scale=float(config.get("tts_length_scale", 0.9)),
            sentence_silence=float(config.get("tts_sentence_silence", 0.12)),
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
        self._set_status("Starting", "Initializing local assistant...")
        self.memory.load()
        self._install_shutdown_handlers()
        self._start_status_gui_if_enabled()
        self._preflight()
        self._start_tray_if_enabled()
        self.tts.speak("Jarvis is ready.")

        mode = str(self.config.get("listening_mode", "push_to_talk")).lower()
        if mode in {"always_on", "vad_wake"}:
            self._always_on_loop()
        elif mode == "wake_word":
            self._wake_word_loop()
        else:
            self._push_to_talk_loop()

    def _preflight(self) -> None:
        self._set_status("Checking", "Testing microphone and local model...")
        try:
            self.recorder.check_microphone()
        except AudioRecorderError as exc:
            self.log.error("Microphone error: %s", exc)
            self._set_status("Mic Error", str(exc))
            self.tts.speak("I cannot find a working microphone. Check the log.")

        ollama_ready = False
        try:
            models = self.llm.list_models()
            ollama_ready = True
            if self.config["model"] not in models:
                self.log.warning(
                    "Ollama model %s was not found. Installed models: %s",
                    self.config["model"],
                    ", ".join(models) or "(none)",
                )
        except OllamaError as exc:
            if self.config.get("auto_start_ollama", True):
                self._set_status("Starting Ollama", "Local model server was not running.")
                self.log.warning("Ollama not ready, trying to start it: %s", exc)
                self._start_ollama()
                time.sleep(5)
                try:
                    self.llm.list_models()
                    ollama_ready = True
                    self.log.info("Ollama started successfully")
                    self._set_status("Ready", "Ollama is running.")
                except OllamaError as retry_exc:
                    exc = retry_exc
            if not ollama_ready:
                self.log.error("Ollama preflight failed: %s", exc)
                self._set_status("Ollama Error", str(exc))
                self.tts.speak("Ollama is not ready. Start Ollama and check the log.")

        if self.config.get("ollama_warmup", True):
            try:
                self._set_status("Warming Model", "Keeping Ollama hot for faster replies...")
                self.llm.warmup()
            except OllamaError as exc:
                self.log.warning("Ollama warmup skipped: %s", exc)

        if self.config.get("stt_warmup", True):
            try:
                self._set_status("Warming STT", "Loading Whisper before the first command...")
                self.stt._load_model()
                self.log.info(
                    "STT ready on %s (%s)",
                    self.stt.active_device or self.config.get("whisper_device"),
                    self.stt.active_compute_type or self.config.get("whisper_compute_type"),
                )
            except SpeechToTextError as exc:
                self.log.warning("STT warmup skipped: %s", exc)

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
        self._set_status("Listening", f"Hold {key} to speak.")
        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.2)
                continue
            if self._run_queued_typed_commands():
                time.sleep(0.1)
                continue
            if self.force_command_event.is_set():
                self.force_command_event.clear()
                self._set_status("Force Listen", "Speak now.")
                try:
                    audio_path = self.recorder.record_until_silence(
                        stop_event=self.stop_event,
                        speech_threshold=float(self.config.get("vad_speech_threshold", 0.018)),
                        silence_seconds=float(self.config.get("vad_silence_seconds", 0.9)),
                        min_record_seconds=float(self.config.get("vad_min_record_seconds", 1.4)),
                        max_record_seconds=float(self.config.get("always_on_chunk_seconds", 5)),
                        start_timeout_seconds=float(
                            self.config.get("force_listen_start_timeout_seconds", 8)
                        ),
                    )
                except AudioRecorderError as exc:
                    self.log.error("Force recording failed: %s", exc)
                    self._set_status("Audio Error", str(exc))
                    continue
                if audio_path is not None:
                    self._handle_audio(audio_path)
                continue

            try:
                self._set_status("Listening", f"Hold {key} to speak.")
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
        self._set_status("Listening", f"Say {wake_word} before a command.")
        self.tts.speak("Wake word mode is on.")

        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.5)
                continue
            if self._run_queued_typed_commands():
                time.sleep(0.1)
                continue
            if self.force_command_event.is_set():
                self.force_command_event.clear()
                self._set_status("Force Listen", "Speak now.")
                try:
                    forced_audio = self.recorder.record_until_silence(
                        stop_event=self.stop_event,
                        speech_threshold=float(self.config.get("vad_speech_threshold", 0.018)),
                        silence_seconds=float(self.config.get("vad_silence_seconds", 0.9)),
                        min_record_seconds=float(self.config.get("vad_min_record_seconds", 1.4)),
                        max_record_seconds=float(self.config.get("always_on_chunk_seconds", 5)),
                        start_timeout_seconds=float(
                            self.config.get("force_listen_start_timeout_seconds", 8)
                        ),
                    )
                except AudioRecorderError as exc:
                    self.log.error("Force recording failed: %s", exc)
                    self._set_status("Audio Error", str(exc))
                    continue
                if forced_audio is not None:
                    self._handle_audio(forced_audio)
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
                self._set_status("Transcribing", "Checking for wake word...")
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
                if text:
                    self._set_status("Ignored", f"No wake word: {self._short(text)}")
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
        use_vad = bool(self.config.get("always_on_use_vad", True))
        require_wake_word = (
            str(self.config.get("listening_mode", "")).lower() == "vad_wake"
            or bool(self.config.get("wake_word_required", False))
        )
        wake_word = str(self.config.get("wake_word", "jarvis")).lower()
        self.log.info(
            "Listening in %s mode%s",
            "VAD wake-word" if require_wake_word else "always-on hands-free",
            " with VAD endpointing" if use_vad else "",
        )
        if require_wake_word:
            self._set_status("Listening", f"Say {wake_word} before a command.")
            self.tts.speak("Ready. Say Jarvis before a command.")
        else:
            self._set_status("Listening", "Speak normally.")
            self.tts.speak("Hands-free mode is on.")

        while not self.stop_event.is_set():
            if not self.listening_enabled.is_set():
                time.sleep(0.5)
                continue
            if self._run_queued_typed_commands():
                time.sleep(0.1)
                continue

            forced_capture = self.force_command_event.is_set()
            audio_path = None
            try:
                self._set_status(
                    "Force Listen" if forced_capture else "Listening",
                    "Speak now. Wake word is not required."
                    if forced_capture
                    else (
                        f"Say {wake_word} before a command."
                        if require_wake_word
                        else "Speak normally."
                    ),
                )
                if use_vad:
                    if forced_capture:
                        self.force_command_event.clear()
                    audio_path = self.recorder.record_until_silence(
                        stop_event=self.stop_event,
                        interrupt_event=None if forced_capture else self.force_command_event,
                        speech_threshold=float(
                            self.config.get("vad_speech_threshold", 0.018)
                        ),
                        silence_seconds=float(
                            self.config.get("vad_silence_seconds", 0.9)
                        ),
                        min_record_seconds=float(
                            self.config.get("vad_min_record_seconds", 1.4)
                        ),
                        max_record_seconds=chunk_seconds,
                        start_timeout_seconds=float(
                            self.config.get(
                                "force_listen_start_timeout_seconds"
                                if forced_capture
                                else "vad_start_timeout_seconds",
                                8 if forced_capture else 10,
                            )
                        ),
                    )
                else:
                    audio_path = self.recorder.record_for(
                        seconds=chunk_seconds,
                        stop_event=self.stop_event,
                    )
                if audio_path is None:
                    continue
                if self._handle_double_clap_if_detected(audio_path):
                    continue
                self._set_status("Transcribing", "Processing your voice...")
                stt_started = time.perf_counter()
                text = self.stt.transcribe(audio_path).strip()
                self.log.info("Transcription completed in %.2fs", time.perf_counter() - stt_started)
                forced_capture = forced_capture or self.force_command_event.is_set()
                self.force_command_event.clear()
                if text:
                    self._set_status("Transcribed", self._short(text))
            except (AudioRecorderError, SpeechToTextError) as exc:
                self.log.error("Always-on listening pass failed: %s", exc)
                self._set_status("Audio Error", str(exc))
                time.sleep(1.0)
                continue
            finally:
                if audio_path is not None:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            if not text:
                self._set_status("Ignored", "Heard audio, but no speech was recognized.")
                continue
            if forced_capture:
                self.log.info("Forced user said: %s", text)
                self._set_status("Heard", self._short(text))
                self._handle_text(text)
                self._set_status("Complete", "Answer delivered. Returning to listening...")
                time.sleep(0.35)
                continue
            if len(text) < min_chars:
                self.log.info("Ignored short always-on transcript: %s", text)
                self._set_status("Ignored", f"Too short: {self._short(text)}")
                continue
            if self._looks_like_background_noise(text):
                self.log.info("Ignored likely background transcript: %s", text)
                self._set_status("Ignored", f"Background: {self._short(text)}")
                continue
            if self._looks_like_code_or_logs(text):
                self.log.info("Ignored code-like transcript: %s", text)
                self._set_status("Ignored", "Code/log-like audio was ignored.")
                continue
            if require_wake_word:
                request = self._extract_wake_request(text, wake_word)
                if request is None:
                    self.log.info("Ignored transcript without wake word: %s", text)
                    self._set_status("Ignored", f"No wake word: {self._short(text)}")
                    time.sleep(0.75)
                    continue
                if not request:
                    self._set_status("Ready", "Wake word heard.")
                    self.tts.speak("At your service.")
                    continue
                self.log.info("Wake-word user said: %s", request)
                self._set_status("Heard", self._short(request))
                self._handle_text(request)
                self._set_status("Complete", "Answer delivered. Returning to listening...")
                time.sleep(0.35)
            else:
                self.log.info("Always-on user said: %s", text)
                self._set_status("Heard", self._short(text))
                self._handle_text(text)
                self._set_status("Complete", "Answer delivered. Returning to listening...")
                time.sleep(0.35)

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

    def _extract_wake_request(self, text: str, wake_word: str) -> str | None:
        lower = text.lower()
        variants = {
            wake_word,
            f"hey {wake_word}",
            f"okay {wake_word}",
            f"ok {wake_word}",
        }
        if not any(variant in lower for variant in variants):
            return None
        index = lower.find(wake_word)
        if index == -1:
            return ""
        return text[index + len(wake_word) :].strip(" ,.!?:;-")

    def _looks_like_code_or_logs(self, text: str) -> bool:
        lower = text.lower()
        code_markers = (
            "def ",
            "class ",
            "import ",
            "traceback",
            "exception",
            "syntax error",
            "return ",
            "self.",
            "config.json",
            "main.py",
            "powershell",
            "get-content",
            "start-process",
        )
        marker_count = sum(marker in lower for marker in code_markers)
        symbol_count = sum(text.count(symbol) for symbol in ("{", "}", "(", ")", "=", "\\", "/"))
        return marker_count >= 2 or symbol_count >= 8

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
        self._set_status("Shortcut", "Double clap detected. Opening workspace...")
        self.tts.speak("Opening Codex and VS Code.")
        result = self.tools.run("open_workspace", {})
        self.log.info("Double-clap action result: %s", result.message)
        return True

    def _handle_audio(self, audio_path: Path) -> None:
        try:
            self._set_status("Transcribing", "Processing your voice...")
            started = time.perf_counter()
            text = self.stt.transcribe(audio_path).strip()
            self.log.info("Transcription completed in %.2fs", time.perf_counter() - started)
        except SpeechToTextError as exc:
            self.log.error("Transcription failed: %s", exc)
            self._set_status("STT Error", str(exc))
            self.tts.speak("I could not transcribe that. Check the log.")
            return
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass

        if not text:
            self.log.info("Ignored empty transcript")
            self._set_status("Ignored", "Heard audio, but no speech was recognized.")
            return
        self.log.info("User said: %s", text)
        self._set_status("Heard", self._short(text))
        self._handle_text(text)

    def _handle_text(self, user_text: str) -> None:
        turn_started = time.perf_counter()
        self._set_status("Thinking", self._short(user_text))
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.memory.messages)
        messages.append({"role": "user", "content": user_text})

        try:
            llm_started = time.perf_counter()
            assistant_text = self.llm.chat(messages)
            self.log.info("LLM first response completed in %.2fs", time.perf_counter() - llm_started)
        except OllamaError as exc:
            self.log.error("Ollama chat failed: %s", exc)
            self._set_status("LLM Error", str(exc))
            self.tts.speak(str(exc))
            return

        tool_request = self.tools.parse_tool_request(assistant_text)
        if tool_request is None:
            self.memory.add("user", user_text)
            self.memory.add("assistant", assistant_text)
            self._set_status(
                "Speaking",
                f"{self._short(assistant_text, 82)} ({time.perf_counter() - turn_started:.1f}s)",
            )
            self.tts.speak(assistant_text)
            self.memory.save()
            return

        final_text = self._run_tool_round(user_text, messages, assistant_text, tool_request)
        self.memory.add("user", user_text)
        self.memory.add("assistant", final_text)
        self.memory.save()
        self._set_status(
            "Speaking",
            f"{self._short(final_text, 82)} ({time.perf_counter() - turn_started:.1f}s)",
        )
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
        self._set_status("Tool", f"{tool_name}: {reason}")

        if self.tools.requires_confirmation(tool_name) and self.config.get(
            "require_tool_confirmation", True
        ):
            if not self._confirm_tool(tool_name, args, reason):
                return f"Cancelled {tool_name}."

        result = self.tools.run(tool_name, args)
        self.log.info("Tool result: %s", result.message)
        self._set_status("Tool Done", self._short(result.message))

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

    def _start_status_gui_if_enabled(self) -> None:
        if not self.config.get("enable_status_gui", False):
            return
        try:
            from status_gui import StatusGui

            self.status_gui = StatusGui(
                logging.getLogger("jarvis.status_gui"),
                fullscreen=bool(self.config.get("status_gui_fullscreen", False)),
            )
            self.status_gui.start_with_callbacks(
                stop_callback=self._stop_from_gui,
                force_callback=self._force_next_command,
                toggle_listening_callback=self._toggle_listening,
                typed_command_callback=self._queue_typed_command,
                open_logs_callback=self._open_logs,
                open_project_callback=self._open_project,
            )
            self.log.info("Status GUI enabled")
        except Exception as exc:
            self.log.warning("Status GUI unavailable: %s", exc)

    def _stop_from_gui(self) -> None:
        self.log.info("GUI stop requested")
        self.stop_event.set()
        self.memory.save()

    def _force_next_command(self) -> None:
        self.log.info("GUI force-listen requested")
        self.force_command_event.set()
        self.listening_enabled.set()
        self._set_status("Force Listen", "Speak now. Wake word and short-text filters are bypassed.")

    def _toggle_listening(self) -> None:
        if self.listening_enabled.is_set():
            self.listening_enabled.clear()
            self._set_status("Paused", "Listening is paused.")
            self.log.info("Listening paused from GUI")
            return
        self.listening_enabled.set()
        self._set_status("Listening", "Listening resumed.")
        self.log.info("Listening resumed from GUI")

    def _queue_typed_command(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            return
        self.log.info("GUI typed command queued: %s", clean)
        self.typed_command_queue.put(clean)
        self.listening_enabled.set()
        self._set_status("Typed", self._short(clean))

    def _open_logs(self) -> None:
        log_path = resolve_app_path(self.config["log_file"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch(exist_ok=True)
        subprocess.Popen(
            ["notepad.exe", str(log_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def _open_project(self) -> None:
        result = self.tools.run("open_workspace", {})
        self.log.info("GUI open project result: %s", result.message)
        self._set_status("Shortcut", result.message)

    def _run_queued_typed_commands(self) -> bool:
        handled = False
        while not self.typed_command_queue.empty() and not self.stop_event.is_set():
            try:
                text = self.typed_command_queue.get_nowait()
            except queue.Empty:
                break
            handled = True
            self.log.info("GUI typed command: %s", text)
            self._set_status("Heard", self._short(text))
            self._handle_text(text)
            self._set_status("Complete", "Answer delivered. Returning to listening...")
        return handled

    def _set_status(self, state: str, detail: str = "") -> None:
        if self.status_gui is not None:
            self.status_gui.update(state, detail)

    def _short(self, text: str, limit: int = 96) -> str:
        clean = " ".join(str(text).split())
        if len(clean) <= limit:
            return clean
        return clean[: limit - 3] + "..."

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
