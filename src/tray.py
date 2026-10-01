"""Tray icon (bottom right in the Windows taskbar) instead of a console window."""
import subprocess
import sys
import threading
import time

PINK = (255, 79, 163, 255)
WHITE = (255, 255, 255, 255)


def create_icon_image(size=64):
    """Pink rounded square with a white progress bar – also used for the .exe icon."""
    from PIL import Image, ImageDraw

    scale = 4  # draw large and shrink for smooth edges
    big = size * scale
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=PINK)
    # Bar track and filled part
    left, right = big * 0.18, big * 0.82
    top, bottom = big * 0.56, big * 0.72
    radius = (bottom - top) / 2
    draw.rounded_rectangle((left, top, right, bottom), radius=radius, outline=WHITE, width=int(big * 0.035))
    draw.rounded_rectangle((left, top, left + (right - left) * 0.65, bottom), radius=radius, fill=WHITE)
    # Nozzle (small triangle) above the bar
    cx = left + (right - left) * 0.65
    draw.polygon([(cx - big * 0.11, big * 0.26), (cx + big * 0.11, big * 0.26), (cx, big * 0.45)], fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


def copy_to_clipboard(text):
    if sys.platform == 'win32':
        subprocess.run(['clip'], input=text.encode('utf-16-le'), creationflags=0x08000000, check=False)


def run_tray(get_status_text, open_settings, overlay_url, on_quit):
    """Shows the tray icon and blocks until "Beenden" is chosen. Returns False if no tray is available."""
    try:
        import pystray
    except Exception as e:
        print(f"Tray icon not available: {e}")
        return False

    def quit_app(icon, item):
        icon.visible = False
        icon.stop()
        on_quit()

    menu = pystray.Menu(
        pystray.MenuItem('Einstellungen öffnen', lambda icon, item: open_settings(), default=True),
        pystray.MenuItem('Overlay-Adresse kopieren', lambda icon, item: copy_to_clipboard(overlay_url)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Beenden', quit_app),
    )
    icon = pystray.Icon('Bambu2OBS', create_icon_image(), 'Bambu2OBS', menu)

    def keep_title_updated():
        while True:
            try:
                icon.title = f"Bambu2OBS – {get_status_text()}"
            except Exception:
                pass
            time.sleep(3)

    def on_ready(icon):
        icon.visible = True
        threading.Thread(target=keep_title_updated, daemon=True).start()
        try:
            icon.notify('Bambu2OBS läuft hier unten in der Taskleiste. Rechtsklick für das Menü.', 'Bambu2OBS')
        except Exception:
            pass

    try:
        icon.run(setup=on_ready)
    except Exception as e:
        print(f"Tray icon failed: {e}")
        return False
    return True
