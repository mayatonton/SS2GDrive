from __future__ import annotations
import os, sys, json, time, signal, shlex, subprocess, threading
from typing import Optional, Tuple, Dict, Any, List

from .screencast_portal import start_screencast_session
from .config import ensure_videos_dir, get_screencast_restore_token, load_settings
from .drive_uploader import upload_and_share
from .clipboard import copy_to_clipboard
from .notify import notify

DEBUG = bool(os.environ.get("SS2GD_DEBUG"))
def _dbg(msg: str) -> None:
    if DEBUG: print(f"[rec] {msg}", file=sys.stderr, flush=True)

# ------ state file ------
def _config_dir() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = xdg if xdg else os.path.expanduser("~/.config")
    d = os.path.join(base, "ss2gdrive")
    os.makedirs(d, exist_ok=True)
    return d
STATE_PATH = os.path.join(_config_dir(), "record_state.json")
def _save_state(d: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f: json.dump(d, f)
def _load_state() -> Optional[Dict[str, Any]]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return None
def _clear_state() -> None:
    try: os.remove(STATE_PATH)
    except Exception: pass

# ------ audio detection ------
def _list_sources() -> List[str]:
    try:
        r = subprocess.run(["pactl", "list", "short", "sources"],
                           capture_output=True, text=True, check=False)
        out = []
        for ln in r.stdout.splitlines():
            cols = ln.split()
            if len(cols) >= 2:
                out.append(cols[1])
        return out
    except Exception as e:
        _dbg(f"pactl list sources failed: {e}")
        return []

def _detect_monitor_source() -> Optional[str]:
    # 1) 環境変数が最優先
    env = os.environ.get("SS2GD_AUDIO_MONITOR")
    if env:
        _dbg(f"audio monitor from env: {env}")
        return env

    # 2) 設定（audio.mode: auto | none | device）
    st = load_settings() or {}
    audio = st.get("audio") or {}
    mode = (audio.get("mode") or "auto").lower().strip()

    if mode == "none":
        _dbg("audio mode: none")
        return None

    if mode == "device":
        # ★ ユーザー指定を厳密に優先（列挙一致チェックで落とさない）
        dev = (audio.get("device") or "").strip()
        if dev:
            _dbg(f"audio mode: device -> {dev}")
            return dev
        _dbg("audio mode: device but no device specified")
        return None

    # 3) 自動（Default Sink の .monitor → 無ければ最初の monitor）
    try:
        r = subprocess.run(["pactl","info"], capture_output=True, text=True, check=False)
        sink = None
        for line in r.stdout.splitlines():
            if "Default Sink:" in line:
                sink = line.split(":",1)[1].strip(); break
        if sink:
            cand = sink + ".monitor"
            _dbg(f"audio monitor from default sink: {cand}")
            return cand
        r2 = subprocess.run(["pactl","list","short","sources"], capture_output=True, text=True, check=False)
        for ln in r2.stdout.splitlines():
            cols = ln.split()
            if len(cols) >= 2 and "monitor" in cols[1]:
                _dbg(f"audio monitor from sources: {cols[1]}")
                return cols[1]
    except Exception as e:
        _dbg(f"pactl detect failed: {e}")
    return None

# ------ gstreamer args ------
def _build_gst_args(fd_num: int, node_id: int, crop: Tuple[int,int,int,int],
                    fps: int, out_path: str, audio_device: Optional[str]) -> List[str]:
    top,left,right,bottom = crop
    args = [
        "gst-launch-1.0", "-e",
        "webmmux", "name=mux", "streamable=true", "!", "filesink", f"location={out_path}", "sync=true",
        # video
        "pipewiresrc", f"fd={fd_num}", f"path={node_id}", "do-timestamp=true",
        "!", "queue", "!", "videoconvert", "!", "videoscale", "!", "videorate",
        "!", f"video/x-raw,format=I420,framerate={fps}/1",
        "!", "videocrop", f"top={top}", f"left={left}", f"right={right}", f"bottom={bottom}",
        "!", "queue", "!", "vp8enc", "deadline=1", "threads=4",
        "!", "queue", "!", "mux.",
    ]
    if audio_device:
        args += [
            "pulsesrc", f"device={audio_device}",
            "!", "audioconvert", "!", "audioresample", "!", "queue",
            "!", "opusenc", "bitrate=128000",
            "!", "queue", "!", "mux.",
        ]
    return args

def _calc_crop(rect: Tuple[int,int,int,int], monitor_pos: Tuple[int,int], monitor_size: Tuple[int,int]) -> Tuple[int,int,int,int]:
    x,y,w,h = rect; mx,my = monitor_pos; mw,mh = monitor_size
    top    = max(0, y - my)
    left   = max(0, x - mx)
    right  = max(0, (mx+mw) - (x+w))
    bottom = max(0, (my+mh) - (y+h))
    return (top,left,right,bottom)

# ------ public API ------
def start_recording(*, fps: int = 30, rect: Tuple[int,int,int,int]) -> str:
    """
    録画を非同期開始。矩形 rect=(x,y,w,h) は **UI で取得して渡すこと**。
    戻り: 出力ファイルパス（まだ中身は録画中）
    """
    if not rect or len(rect) != 4:
        raise ValueError("rect is required: (x,y,w,h)")

    _dbg("start_screencast_session()")
    restore = get_screencast_restore_token()
    fd, streams, _ = asyncio_run(start_screencast_session(restore_token=restore))
    if not streams: raise RuntimeError("screencast: no streams")
    s = streams[0]
    node_id = int(s["node_id"])
    mon_pos = s.get("position") or (0,0)
    mon_sz  = s.get("size") or (1920,1080)

    crop = _calc_crop(rect, mon_pos, mon_sz)
    _dbg(f"node_id={node_id} rect={rect} crop={crop}")

    out_dir = ensure_videos_dir()
    base = time.strftime("REC_%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"{base}.webm")

    fd_child = os.dup(fd)
    os.close(fd)

    audio_dev = _detect_monitor_source()
    _dbg(f"audio device resolved: {audio_dev!r}")

    args = _build_gst_args(fd_child, node_id, crop, fps, out_path, audio_dev)
    _dbg("launch gst-launch-1.0")
    p = subprocess.Popen(args, pass_fds=(fd_child,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(fd_child)

    _save_state({"pid": p.pid, "file": out_path})
    try: notify("Recording started")
    except Exception: pass
    _dbg(f"recording pid={p.pid}, out={out_path}")
    return out_path

def stop_recording(*, open_browser: bool = True, copy_link: bool = True) -> Optional[str]:
    """録画停止 → Drive アップロード。リンクを返す。"""
    st = _load_state()
    if not st:
        _dbg("no active state")
        try: notify("No active recording")
        except Exception: pass
        return None

    pid = int(st.get("pid", 0))
    out_path = st.get("file")
    _dbg(f"stopping pid={pid}")

    try: os.kill(pid, signal.SIGINT)  # EOS
    except ProcessLookupError: pass

    # 最大10秒待機
    for _ in range(100):
        try:
            ret = os.waitpid(pid, os.WNOHANG)[1]
            if ret != 0: break
        except ChildProcessError:
            break
        time.sleep(0.1)

    if not out_path or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        _clear_state()
        try: notify("Record failed: no output")
        except Exception: pass
        raise RuntimeError("record failed: no output")

    _dbg(f"saved: {out_path}")
    try: notify("Uploading video…")
    except Exception: pass

    link = upload_and_share(out_path, "video/webm", os.path.basename(out_path))
    _dbg(f"uploaded: {link}")
    try: notify("Uploaded video")
    except Exception: pass

    if copy_link:
        try: copy_to_clipboard(link)
        except Exception as e: _dbg(f"clipboard err: {e}")
    if open_browser:
        try:
            import webbrowser; webbrowser.open(link)
        except Exception as e: _dbg(f"browser err: {e}")

    _clear_state()
    return link

# ---- async helper ----
def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        res = {"v": None, "e": None}
        def worker():
            try: res["v"] = asyncio.run(coro)
            except Exception as e: res["e"] = e
        t = threading.Thread(target=worker, daemon=True); t.start(); t.join()
        if res["e"]: raise res["e"]
        return res["v"]
