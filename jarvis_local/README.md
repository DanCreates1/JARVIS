# Jarvis Local Voice Assistant

A small Windows 11 voice assistant that runs locally:

- Always-on microphone input with VAD endpointing and a "Jarvis" wake phrase
- Fullscreen status GUI with Space-to-force-listen and typed command input
- `faster-whisper` speech-to-text with low-latency speech endpointing
- CUDA-preferred `faster-whisper` on NVIDIA GPUs, with CPU fallback
- Ollama chat at `http://localhost:11434/api/chat` with keep-alive warmup
- Piper text-to-speech
- Short local conversation memory
- Safe, confirmed tools for Notepad, Chrome, time, notes, and text-file reading
- Background startup with `pythonw.exe`

Version 1 is intentionally simple, stable, and fast.

## Hardware Target

This setup is sized for:

- Intel i5-11400
- RTX 2050
- 16 GB RAM

Use small models. The default is `qwen2.5:3b`; `llama3.2:3b` is also a good option.

## Project Layout

```text
jarvis_local/
  main.py
  status_gui.py
  config.json
  requirements.txt
  requirements-cuda.txt
  README.md
  logs/
  tools/
    system_tools.py
  audio/
    recorder.py
    stt.py
    tts.py
  llm/
    ollama_client.py
  memory/
    session_memory.py
  scripts/
    run_jarvis.bat
    install_startup_folder.ps1
    install_task_scheduler.ps1
```

## 1. Install Python 3.11

Install Python 3.11 for Windows. During install, enable:

- Add python.exe to PATH
- py launcher

Check it:

```powershell
py -3.11 --version
where.exe pythonw
```

## 2. Create A Virtual Environment

From this folder:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For NVIDIA Whisper acceleration, also run:

```powershell
pip install -r requirements-cuda.txt
```

The app adds the installed CUDA DLL folders automatically at runtime. If CUDA is not usable, Whisper falls back to CPU instead of crashing.

This installs `faster-whisper`, `sounddevice`, `keyboard`, `requests`, and the Piper Python package.

`faster-whisper` may download `base.en` the first time it loads. Do that once during setup, or set `whisper_model` to a local model folder if you need the machine to stay fully offline after installation.

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Install Ollama And Pull The Model

Install Ollama for Windows, then pull the default model:

```powershell
ollama run qwen2.5:3b
```

After the model downloads, you can stop the chat with `/bye`.

Alternative:

```powershell
ollama run llama3.2:3b
```

Then update `config.json`:

```json
{
  "model": "llama3.2:3b"
}
```

## 4. Install Piper Voice Files

The assistant uses Piper locally. Runtime speech does not use cloud APIs.

Put these two files in `voices/`:

```text
voices/en_US-lessac-medium.onnx
voices/en_US-lessac-medium.onnx.json
```

You can use a different Piper voice by changing these fields in `config.json`:

```json
{
  "voice": "en_US-lessac-medium",
  "piper_exe": "piper",
  "piper_model_path": "voices/en_US-lessac-medium.onnx",
  "piper_config_path": "voices/en_US-lessac-medium.onnx.json"
}
```

If `piper` is not on PATH, set `piper_exe` to the full path to `piper.exe`. If the `piper-tts` package does not install cleanly on your machine, use the Piper Windows release and point `piper_exe` at that `piper.exe`.

## 5. Run In Debug Mode

Debug mode shows errors in the terminal:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
.\.venv\Scripts\Activate.ps1
python main.py
```

The current default mode is hands-free:

- Say `Jarvis` before a command.
- If the fullscreen GUI is focused, press `Space`, then speak. This bypasses the wake phrase for the next command.
- Type a command in the text box and press `Enter` if you want to test the LLM without using the microphone.
- Press `Pause / Resume` to stop or restart listening.
- Press `Stop Jarvis` to turn it off.

## 6. Run In Background Mode

Background mode has no visible terminal:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
.\.venv\Scripts\pythonw.exe main.py
```

The fullscreen status GUI still appears if `"enable_status_gui": true`. There is no terminal window.

Logs are written to:

```text
logs/jarvis.log
```

## 7. Tools And Confirmation

The LLM can request these tools:

- `open_notepad`
- `open_chrome`
- `get_time`
- `create_note`
- `read_text_file`

By default on this setup, confirmation is disabled with:

```json
{
  "require_tool_confirmation": false
}
```

Set it back to `true` if you want Jarvis to ask before opening apps, writing notes, or reading files.

Notes are saved under:

```text
notes/
```

Text-file reading is restricted to folders listed in `allowed_read_dirs` in `config.json`.

## 8. Enable Startup - Method A: Startup Folder

This copies a launcher into your Windows Startup folder:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
.\scripts\install_startup_folder.ps1
```

Manual method:

1. Press `Win + R`
2. Run `shell:startup`
3. Create a batch file named `Jarvis Local Assistant.bat`
4. Put this inside it, adjusting the path if you moved the project:

```bat
@echo off
cd /d "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
start "" "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local\.venv\Scripts\pythonw.exe" "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local\main.py"
```

The launcher runs:

```bat
pythonw.exe main.py
```

## 9. Enable Startup - Method B: Task Scheduler

This creates a hidden logon task that runs with highest privileges:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
.\scripts\install_task_scheduler.ps1
```

Remove it later with:

```powershell
.\scripts\uninstall_task_scheduler.ps1
```

## 10. Optional Tray Icon

Tray support is off by default. To enable it:

```powershell
pip install pillow pystray
```

Then set:

```json
{
  "enable_tray": true
}
```

The tray menu supports:

- Start/Stop listening
- Exit

## 11. Optional Wake Word Mode

Push-to-talk is recommended for low latency and low idle CPU.

Wake-word mode is lightweight and simple, not a dedicated hotword engine. It records short chunks and checks for the word "Jarvis", which uses more CPU than push-to-talk.

To try it:

```json
{
  "listening_mode": "wake_word",
  "wake_word": "jarvis"
}
```

## 12. Debugging

Open:

```text
logs/jarvis.log
```

Common issues:

- Missing microphone: check Windows microphone privacy settings and default input device.
- Ollama not running: start Ollama and run `ollama list`.
- Model not found: run `ollama run qwen2.5:3b`.
- Piper missing voice: confirm the `.onnx` and `.onnx.json` files are in `voices/`.
- Push-to-talk not detected: run the assistant as administrator, or change `push_to_talk_key`.
- GPU Whisper load fails: install `requirements-cuda.txt`; the app still falls back to CPU automatically.
- No response after speaking: check the fullscreen GUI state. It should go `Listening` -> `Transcribing` -> `Thinking` -> `Speaking`.
- Discord or another app using the mic: Windows can share most microphones, but disable exclusive mode if Jarvis sees silence.

## 13. Change Models

Pull a small model:

```powershell
ollama run llama3.2:3b
```

Update:

```json
{
  "model": "llama3.2:3b"
}
```

For speech-to-text, `tiny.en` is the lowest-latency default:

```json
{
  "whisper_model": "tiny.en"
}
```

Use `base.en` for better accuracy if `tiny.en` mishears you too often. Use `small.en` only if you can tolerate slower responses.

## 14. Latency Tuning

The fastest mode uses speech endpointing instead of fixed 5-second chunks:

```json
{
  "listening_mode": "always_on",
  "always_on_use_vad": true,
  "vad_silence_seconds": 0.65,
  "whisper_model": "tiny.en"
}
```

Lower `vad_silence_seconds` for faster cut-off after you stop speaking. Raise it if Jarvis cuts you off too early.

Ollama is kept warm with:

```json
{
  "ollama_keep_alive": "30m",
  "ollama_num_ctx": 2048,
  "ollama_num_predict": 96
}
```

Shorter `ollama_num_predict` values make replies faster. Longer values let the model speak more, but they add latency.

The voice is configured as JARVIS-inspired: concise, composed, and polished. It cannot exactly clone the Iron Man voice, but you can swap Piper voices in `config.json`.
