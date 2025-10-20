import argparse, asyncio, os, signal, sys, webbrowser
from .screenshot_portal import take_interactive_screenshot
from .drive_uploader import upload_and_share, sign_in
from .clipboard import copy_to_clipboard, _flush_clipboard
from .config import load_settings, PID_PATH

def cmd_auth():
    ok = sign_in(interactive=True); print("Signed in" if ok else "Not authorized")

def cmd_quit():
    if not os.path.exists(PID_PATH):
        print("No tray pidfile; tray may not be running"); return 1
    try:
        with open(PID_PATH,"r") as f: pid=int(f.read().strip())
        os.kill(pid, signal.SIGTERM); print(f"Sent SIGTERM to tray (pid {pid})"); return 0
    except Exception as e:
        print(f"Failed to quit tray: {e}"); return 1

def cmd_shot():
    import traceback, os
    os.environ.setdefault("SS2GD_DEBUG","1")
    print("[cli] take_interactive_screenshot()", flush=True)
    path = asyncio.run(take_interactive_screenshot())
    copy_to_clipboard("Uploading to Google Drive…")
    try:
        st=load_settings()
        mime = "image/jpeg" if (st.get("image_format")=="jpeg") else "image/png"
        print(f"[cli] uploading {path} as {mime}", flush=True)
        link = upload_and_share(path, mime_type=mime)
        copy_to_clipboard(link); print(link, flush=True); _flush_clipboard(1200)
        try: webbrowser.open(link)
        except Exception: pass
    except Exception as e:
        copy_to_clipboard(f"Upload failed: {e}"); _flush_clipboard(1200)
        traceback.print_exc(); sys.exit(1)
    finally:
        try: os.remove(path)
        except Exception: pass

def cmd_settings():
    from .ui.settings import SettingsDialog
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication(sys.argv)
    SettingsDialog().exec()

def cmd_tray(force_window: bool = False):
    from .ui.tray import TrayApp
    TrayApp(force_window=force_window).run()

def main():
    ap=argparse.ArgumentParser(prog="ss2gd")
    sub=ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth"); sub.add_parser("shot")
    p_tray=sub.add_parser("tray"); p_tray.add_argument("--window", action="store_true")
    sub.add_parser("settings"); sub.add_parser("quit")
    a=ap.parse_args()
    if a.cmd=="auth": cmd_auth()
    elif a.cmd=="shot": cmd_shot()
    elif a.cmd=="tray": cmd_tray(force_window=getattr(a,"window",False))
    elif a.cmd=="settings": cmd_settings()
    elif a.cmd=="quit": sys.exit(cmd_quit())
