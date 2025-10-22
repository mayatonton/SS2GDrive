# app/ss2gd/cli.py
import os, sys, argparse, webbrowser, time

from .screenshot_portal import take_interactive_screenshot, PortalError
from .drive_uploader import upload_and_share, sign_in
from .clipboard import copy_to_clipboard, keep_clipboard_alive

def _debug(msg: str):
    if os.environ.get("SS2GD_DEBUG"):
        print(f"[cli] {msg}", flush=True)

# ---- commands ----

def cmd_shot():
    """矩形スクショ → Drive アップロード → クリップボード & ブラウザ"""
    _debug("take_interactive_screenshot()")
    try:
        # attempt 1
        path = take_interactive_screenshot()
    except PortalError as e1:
        _debug(f"portal error attempt1: {e1}")
        # 短い待ちを挟んで attempt 2
        time.sleep(float(os.environ.get("SS2GD_SHOT_RETRY_DELAY", "0.6")))
        try:
            path = take_interactive_screenshot()
        except PortalError as e2:
            print(f"Screenshot failed: {e2}", file=sys.stderr)
            sys.exit(1)

    # 拡張子からMIME推定（設定ダイアログのformatとも整合）
    mime = "image/png"
    if path.lower().endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"

    link = upload_and_share(path, mime, os.path.basename(path))

    # クリップボード（失敗しても続行）
    try:
        copy_to_clipboard(link)
        keep_clipboard_alive(1500)
    except Exception:
        pass

    # 必ずブラウザも開く
    try:
        webbrowser.open(link)
    except Exception:
        pass

    print(link)

def cmd_auth():
    """Googleサインイン（必要なら）"""
    sign_in(interactive=True)
    print("Signed in")

def cmd_settings():
    """設定ダイアログを単体表示"""
    from PySide6.QtWidgets import QApplication
    from .ui.settings import SettingsDialog
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = SettingsDialog()
    dlg.exec()

def cmd_tray(args):
    """トレイ（フォールバック小ウィンドウあり）"""
    from .ui.tray import TrayApp
    app = TrayApp(force_window=getattr(args, "window", False))
    app.run()

def cmd_record(args):
    """矩形録画 → WebM保存 → Driveにアップロード → クリップボード & ブラウザ"""
    from .record_region import record_region_to_file, upload_recorded_file
    dur = int(getattr(args, "duration", 5))
    fps = int(getattr(args, "fps", 30))
    _debug(f"record duration={dur}s fps={fps}")

    path = record_region_to_file(duration_sec=dur, framerate=fps)
    link = upload_recorded_file(path)

    try:
        copy_to_clipboard(link)
        keep_clipboard_alive(1500)
    except Exception:
        pass
    try:
        webbrowser.open(link)
    except Exception:
        pass
    print(link)

def cmd_record_ui(_args):
    """Start/Stop ができる録画専用UIを起動（起動直後に矩形選択）"""
    from .ui.record import run_window
    run_window()

# ---- entrypoint ----

def main():
    p = argparse.ArgumentParser(prog="ss2gd")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("shot")
    sub.add_parser("auth")
    sub.add_parser("settings")

    p_tray = sub.add_parser("tray")
    p_tray.add_argument("--window", action="store_true", help="tray不可環境で小ウィンドウを強制")

    p_rec = sub.add_parser("record")
    p_rec.add_argument("--duration", type=int, default=5)
    p_rec.add_argument("--fps", type=int, default=30)

    # ★ 録画UI
    sub.add_parser("record-ui")

    a = p.parse_args()

    if a.cmd == "shot":     return cmd_shot()
    if a.cmd == "auth":     return cmd_auth()
    if a.cmd == "settings": return cmd_settings()
    if a.cmd == "tray":     return cmd_tray(a)
    if a.cmd == "record":   return cmd_record(a)
    if a.cmd == "record-ui":return cmd_record_ui(a)

if __name__ == "__main__":
    main()
