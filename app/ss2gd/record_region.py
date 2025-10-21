# app/ss2gd/record_region.py
from __future__ import annotations
import os, time, subprocess, signal, asyncio, threading, shlex
from typing import Tuple, List

from .screencast_portal import start_screencast_session
from .region_select import select_rect            # (x,y,w,h)
from .config import ensure_videos_dir
from .drive_uploader import upload_and_share
from .clipboard import copy_to_clipboard
from .notify import notify

DEBUG = bool(os.environ.get("SS2GD_DEBUG"))

def _run_async(coro):
    """イベントループ有無に関わらず coro を同期実行"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box, err = {}, {}
    def worker():
        try:
            nl = asyncio.new_event_loop()
            asyncio.set_event_loop(nl)
            box["res"] = nl.run_until_complete(coro)
        except Exception as e:
            err["err"] = e
        finally:
            try: nl.close()
            except Exception: pass
    t = threading.Thread(target=worker, daemon=True)
    t.start(); t.join()
    if "err" in err: raise err["err"]
    return box["res"]

def _build_crop(monitor_pos: Tuple[int,int], monitor_size: Tuple[int,int], rect: Tuple[int,int,int,int]):
    mx, my = monitor_pos
    mw, mh = monitor_size
    x, y, w, h = rect
    left   = max(0, x - mx)
    top    = max(0, y - my)
    right  = max(0, (mx + mw) - (x + w))
    bottom = max(0, (my + mh) - (y + h))
    return left, top, right, bottom

def _gst_try(pipeline: List[str], pass_fds: List[int], duration_sec: int) -> tuple[int, str]:
    """パイプラインを走らせ、SIGINTで終了。returncode と stderr を返す"""
    if DEBUG: print("[record] run:", " ".join(shlex.quote(x) for x in pipeline))
    proc = subprocess.Popen(pipeline, pass_fds=pass_fds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(max(1, int(duration_sec)))
        proc.send_signal(signal.SIGINT)       # -e で EOS
        try:
            ret = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill(); ret = proc.wait()
    finally:
        for fd in pass_fds:
            try: os.close(fd)
            except Exception: pass
    out, err = proc.communicate(timeout=1)
    return ret, (err or "")

def record_region_to_file(duration_sec: int = 5, framerate: int = 30) -> str:
    """
    1) portal で画面共有開始 → (fd, streams)
    2) 矩形選択
    3) pipewiresrc (fd=) + (path/target-object/無指定) を試しつつ、
       videoconvert→videoscale→videorate→caps→videocrop の順で安定化
    4) WebM で保存
    """
    if DEBUG: print("[record] start_screencast_session()")
    fd, streams, _ = _run_async(start_screencast_session())
    if not streams:
        raise RuntimeError("No screencast streams from portal")

    node_id = int(streams[0]["node_id"])
    mon_pos = streams[0]["position"] or (0, 0)
    mon_size = streams[0]["size"] or (0, 0)

    if DEBUG: print("[record] region_select()")
    rect = select_rect()  # (x,y,w,h)
    if not rect or rect[2] <= 0 or rect[3] <= 0:
        raise RuntimeError("Canceled region selection")

    left, top, right, bottom = _build_crop(mon_pos, mon_size, rect)
    if DEBUG:
        print(f"[record] node_id={node_id} monitor_pos={mon_pos} monitor_size={mon_size}")
        print(f"[record] rect={rect} crop={left,top,right,bottom}")

    out_dir = ensure_videos_dir()
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"REC_{ts}.webm")

    # ターゲット指定のバリエーション
    target_variants = [
        ("path", str(node_id)),
        ("target-object", str(node_id)),
        None,  # 無指定
    ]
    # フォーマットのフォールバック
    fmt_variants = ["I420", "BGRx", "RGBA"]
    # フレームレート指定の有無もフォールバック
    fps_variants = [True, False]

    last_err = ""
    for tgt in target_variants:
        for fmt in fmt_variants:
            for use_fps in fps_variants:
                dupfd = os.dup(fd)  # 毎回新しい FD を渡す
                head = ["gst-launch-1.0", "-e", "pipewiresrc", f"fd={dupfd}", "do-timestamp=true"]
                if tgt is not None:
                    key, val = tgt
                    head += [f"{key}={val}"]
                    if DEBUG: print(f"[record] trying {key}={val}, format={fmt}, fps={'on' if use_fps else 'off'}")
                else:
                    if DEBUG: print(f"[record] trying (no target), format={fmt}, fps={'on' if use_fps else 'off'}")

                caps = ["video/x-raw", f"format={fmt}"]
                if use_fps:
                    caps.append(f"framerate={int(framerate)}/1")

                tail = [
                    "!", "queue",
                    "!", "videoconvert",
                    "!", "videoscale",
                    "!", "videorate",
                    "!", ",".join(caps),    # capsfilter
                    "!", "videocrop", f"top={top}", f"left={left}", f"right={right}", f"bottom={bottom}",
                    "!", "queue",
                    "!", "vp8enc", "deadline=1", "threads=4",
                    "!", "webmmux", "streamable=true",
                    "!", "filesink", f"location={out_path}", "sync=true"
                ]

                ret, err = _gst_try(head + tail, pass_fds=[dupfd], duration_sec=duration_sec)
                last_err = err
                if ret == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    if DEBUG: print(f"[record] saved: {out_path}")
                    return out_path
                else:
                    if DEBUG:
                        print(f"[record] variant failed (ret={ret}). stderr:")
                        print(err)
                    try:
                        if os.path.exists(out_path) and os.path.getsize(out_path) == 0:
                            os.remove(out_path)
                    except Exception:
                        pass

    raise RuntimeError("record failed: all variants failed\n" + last_err)

def upload_recorded_file(path: str) -> str:
    link = upload_and_share(path, "video/webm", os.path.basename(path))

    # 通知（2引数）
    notify("SS2GDrive", f"Uploaded video:\n{link}")

    # クリップボードにコピー（フォールバック付き）
    try:
        from .clipboard import copy_to_clipboard, keep_clipboard_alive as _keep
        copy_to_clipboard(link)
        _keep(2000)
    except Exception:
        pass

    # 既定ブラウザで開く（失敗しても無視）
    try:
        import webbrowser
        webbrowser.open(link)
    except Exception:
        pass

    print(link, flush=True)
    return link
