from __future__ import annotations

import queue
import threading
import tkinter as tk
from logging import Logger
from typing import Callable


class StatusGui:
    def __init__(self, logger: Logger, fullscreen: bool = False) -> None:
        self.logger = logger
        self.fullscreen = fullscreen
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()

    def start(self, stop_callback: Callable[[], None]) -> None:
        self.thread = threading.Thread(
            target=self._run,
            args=(
                stop_callback,
                lambda: None,
                lambda: None,
                lambda text: None,
                lambda: None,
                lambda: None,
            ),
            name="jarvis-status-gui",
            daemon=True,
        )
        self.thread.start()
        self.ready.wait(timeout=3)

    def start_with_callbacks(
        self,
        stop_callback: Callable[[], None],
        force_callback: Callable[[], None],
        toggle_listening_callback: Callable[[], None],
        typed_command_callback: Callable[[str], None],
        open_logs_callback: Callable[[], None],
        open_project_callback: Callable[[], None],
    ) -> None:
        self.thread = threading.Thread(
            target=self._run,
            args=(
                stop_callback,
                force_callback,
                toggle_listening_callback,
                typed_command_callback,
                open_logs_callback,
                open_project_callback,
            ),
            name="jarvis-status-gui",
            daemon=True,
        )
        self.thread.start()
        self.ready.wait(timeout=3)

    def update(self, state: str, detail: str = "") -> None:
        self.queue.put((state, detail))

    def _run(
        self,
        stop_callback: Callable[[], None],
        force_callback: Callable[[], None],
        toggle_listening_callback: Callable[[], None],
        typed_command_callback: Callable[[str], None],
        open_logs_callback: Callable[[], None],
        open_project_callback: Callable[[], None],
    ) -> None:
        root = tk.Tk()
        root.title("Jarvis")
        root.geometry("960x540+60+60")
        root.minsize(720, 420)
        root.resizable(True, True)
        root.attributes("-topmost", True)
        root.attributes("-fullscreen", self.fullscreen)
        root.configure(bg="#0b1220")

        state_var = tk.StringVar(value="Starting")
        detail_var = tk.StringVar(value="Initializing local assistant...")
        history_items: list[str] = []

        container = tk.Frame(root, bg="#0b1220")
        container.pack(fill="both", expand=True, padx=48, pady=42)

        title = tk.Label(
            container,
            text="JARVIS",
            font=("Segoe UI", 34, "bold"),
            fg="#7dd3fc",
            bg="#0b1220",
        )
        title.pack(anchor="w")

        state = tk.Label(
            container,
            textvariable=state_var,
            font=("Segoe UI", 64, "bold"),
            fg="#f8fafc",
            bg="#0b1220",
        )
        state.pack(anchor="w", pady=(22, 0))

        detail = tk.Label(
            container,
            textvariable=detail_var,
            font=("Segoe UI", 22),
            fg="#cbd5e1",
            bg="#0b1220",
            wraplength=1100,
            justify="left",
        )
        detail.pack(anchor="w", pady=(12, 28))

        hint = tk.Label(
            container,
            text="Say \"Jarvis\" before a command. Press Space while this screen is focused to force the next command.",
            font=("Segoe UI", 12),
            fg="#64748b",
            bg="#0b1220",
        )
        hint.pack(anchor="w", pady=(0, 20))

        entry_frame = tk.Frame(container, bg="#0b1220")
        entry_frame.pack(fill="x", pady=(0, 18))

        command_entry = tk.Entry(
            entry_frame,
            font=("Segoe UI", 16),
            bg="#111827",
            fg="#f8fafc",
            insertbackground="#7dd3fc",
            relief="flat",
        )
        command_entry.pack(side="left", fill="x", expand=True, ipady=9)

        def send_typed_command(_event=None) -> None:
            text = command_entry.get().strip()
            if not text:
                return
            command_entry.delete(0, "end")
            typed_command_callback(text)

        send_button = tk.Button(
            entry_frame,
            text="Send",
            command=send_typed_command,
            font=("Segoe UI", 13, "bold"),
            bg="#0369a1",
            fg="#f8fafc",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        send_button.pack(side="left", padx=(12, 0))

        command_entry.bind("<Return>", send_typed_command)

        history = tk.Text(
            container,
            height=7,
            font=("Consolas", 12),
            bg="#020617",
            fg="#cbd5e1",
            relief="flat",
            wrap="word",
        )
        history.pack(fill="both", expand=True, pady=(0, 18))
        history.insert("end", "Status history will appear here.\n")
        history.configure(state="disabled")

        def on_stop() -> None:
            stop_callback()
            root.destroy()

        controls = tk.Frame(container, bg="#0b1220")
        controls.pack(anchor="w")

        button = tk.Button(
            controls,
            text="Stop Jarvis",
            command=on_stop,
            font=("Segoe UI", 14),
            bg="#1e293b",
            fg="#f8fafc",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        button.pack(side="left", padx=(0, 10))

        force_button = tk.Button(
            controls,
            text="Force Listen (Space)",
            command=force_callback,
            font=("Segoe UI", 14),
            bg="#0f766e",
            fg="#f8fafc",
            activebackground="#14b8a6",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        force_button.pack(side="left", padx=(0, 10))

        pause_button = tk.Button(
            controls,
            text="Pause / Resume",
            command=toggle_listening_callback,
            font=("Segoe UI", 14),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        pause_button.pack(side="left", padx=(0, 10))

        logs_button = tk.Button(
            controls,
            text="Open Logs",
            command=open_logs_callback,
            font=("Segoe UI", 14),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        logs_button.pack(side="left", padx=(0, 10))

        project_button = tk.Button(
            controls,
            text="Open Project",
            command=open_project_callback,
            font=("Segoe UI", 14),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=9,
        )
        project_button.pack(side="left")

        def toggle_fullscreen(_event=None) -> None:
            current = bool(root.attributes("-fullscreen"))
            root.attributes("-fullscreen", not current)

        root.bind("<F11>", toggle_fullscreen)
        root.bind("<Escape>", toggle_fullscreen)

        def force_from_space(event=None) -> str | None:
            if root.focus_get() == command_entry:
                return None
            force_callback()
            return "break"

        root.bind("<space>", force_from_space)

        def poll() -> None:
            try:
                while True:
                    next_state, next_detail = self.queue.get_nowait()
                    state_var.set(next_state)
                    detail_var.set(next_detail)
                    history_items.append(
                        f"{next_state}: {next_detail}" if next_detail else next_state
                    )
                    del history_items[:-40]
                    history.configure(state="normal")
                    history.delete("1.0", "end")
                    history.insert("end", "\n".join(history_items) + "\n")
                    history.see("end")
                    history.configure(state="disabled")
            except queue.Empty:
                pass
            root.after(120, poll)

        root.protocol("WM_DELETE_WINDOW", root.withdraw)
        self.ready.set()
        poll()
        try:
            root.mainloop()
        except Exception as exc:
            self.logger.warning("Status GUI stopped: %s", exc)
