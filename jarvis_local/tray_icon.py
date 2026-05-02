from __future__ import annotations

import threading
from logging import Logger


def start_tray(listening_enabled, stop_event, logger: Logger) -> None:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Install pystray and pillow to enable the tray icon.") from exc

    def make_image() -> Image.Image:
        image = Image.new("RGB", (64, 64), "#111827")
        draw = ImageDraw.Draw(image)
        draw.ellipse((14, 14, 50, 50), fill="#38bdf8")
        draw.ellipse((26, 26, 38, 38), fill="#111827")
        return image

    def toggle(icon, item) -> None:
        if listening_enabled.is_set():
            listening_enabled.clear()
            logger.info("Listening paused from tray")
        else:
            listening_enabled.set()
            logger.info("Listening resumed from tray")
        icon.update_menu()

    def label(item) -> str:
        return "Stop listening" if listening_enabled.is_set() else "Start listening"

    def exit_app(icon, item) -> None:
        logger.info("Exit requested from tray")
        stop_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(label, toggle),
        pystray.MenuItem("Exit", exit_app),
    )
    icon = pystray.Icon("Jarvis Local", make_image(), "Jarvis Local", menu)
    thread = threading.Thread(target=icon.run, name="jarvis-tray", daemon=True)
    thread.start()
