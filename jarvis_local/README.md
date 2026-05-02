# Jarvis Local Voice Assistant

A small Windows 11 voice assistant that runs locally:

- Push-to-talk microphone input with Right Ctrl
- `faster-whisper` speech-to-text
- Ollama chat at `http://localhost:11434/api/chat`
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
  config.json
  requirements.txt
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

Hold Right Ctrl, speak, then release Right Ctrl.

## 6. Run In Background Mode

Background mode has no visible terminal:

```powershell
cd "C:\Users\poyan\OneDrive\Documents\New project\jarvis_local"
.\.venv\Scripts\pythonw.exe main.py
```

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

Tools that open apps, write files, or read files require voice confirmation. Jarvis will ask for confirmation, then you hold Right Ctrl and say "yes" or "cancel".

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
- GPU Whisper load fails: the app falls back to CPU automatically.

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

For speech-to-text, keep `base.en` for speed:

```json
{
  "whisper_model": "base.en"
}
```

You can try `small.en` for better accuracy, but it will be slower.
