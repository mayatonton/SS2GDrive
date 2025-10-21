# app/ss2gd/notify.py
from __future__ import annotations
import shutil, subprocess, sys

def notify(*args):
    """
    notify("Message") あるいは notify("Title", "Message")
    スレッド安全：Qtは使わない。notify-send があれば使い、無ければstderrへ。
    """
    if len(args) == 1:
        title, body = "SS2GDrive", str(args[0])
    elif len(args) >= 2:
        title, body = (str(args[0]) or "SS2GDrive"), str(args[1])
    else:
        return

    exe = shutil.which("notify-send")
    if exe:
        try:
            subprocess.run([exe, title, body], check=False)
            return
        except Exception:
            pass

    # フォールバック（通知コマンドが無い環境）
    try:
        print(f"[notify] {title}: {body}", file=sys.stderr, flush=True)
    except Exception:
        pass
