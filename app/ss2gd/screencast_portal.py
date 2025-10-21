# app/ss2gd/screencast_portal.py
from __future__ import annotations
import os, asyncio, uuid
from typing import Any, Dict, List, Tuple, Sequence
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, Variant

PORTAL   = "org.freedesktop.portal.Desktop"
OBJ      = "/org/freedesktop/portal/desktop"
IF_SC    = "org.freedesktop.portal.ScreenCast"
IF_REQ   = "org.freedesktop.portal.Request"
IF_DBUS  = "org.freedesktop.DBus"

DEBUG = bool(os.environ.get("SS2GD_DEBUG"))

def _v(x):  # 単層 Variant を剥がす
    return x.value if isinstance(x, Variant) else x

def _deep_unvariant(x):  # 深い Variant も Python 素の型へ
    if isinstance(x, Variant):
        return _deep_unvariant(x.value)
    if isinstance(x, dict):
        return {k: _deep_unvariant(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        t = type(x)
        return t(_deep_unvariant(v) for v in x)
    return x

async def _add_match(bus: MessageBus, rule: str) -> None:
    msg = Message(
        destination="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface=IF_DBUS,
        member="AddMatch",
        signature="s",
        body=[rule],
    )
    reply = await bus.call(msg)
    if reply.message_type != MessageType.METHOD_RETURN:
        raise RuntimeError(f"AddMatch failed: {reply.error_name}")
    if DEBUG:
        print(f"[dbus] AddMatch: {rule}")

async def _wait_request_response(bus: MessageBus, handle: str, timeout: float = 60.0) -> Tuple[int, Dict[str, Any]]:
    fut: asyncio.Future = asyncio.get_running_loop().create_future()

    def handler(msg):
        if (msg.message_type == MessageType.SIGNAL and
            msg.interface == IF_REQ and
            msg.member == "Response" and
            msg.path == handle):
            code = msg.body[0]
            results = msg.body[1] if len(msg.body) > 1 else {}
            if DEBUG:
                print(f"[portal] Response code={code}, keys={list(results.keys())}")
            if not fut.done():
                fut.set_result((code, results))
            return True
        return False

    bus.add_message_handler(handler)
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        try:
            bus.remove_message_handler(handler)
        except Exception:
            pass

async def _call_with_handle(bus: MessageBus, interface: str, member: str, signature: str, body: list, timeout: float = 60.0):
    msg = Message(destination=PORTAL, path=OBJ, interface=interface, member=member, signature=signature, body=body)
    reply = await asyncio.wait_for(bus.call(msg), timeout=timeout)
    if reply.message_type != MessageType.METHOD_RETURN:
        raise RuntimeError(f"Portal call failed: {reply.error_name}")
    handle = reply.body[0]  # object path (Request)
    if DEBUG:
        print(f"[portal] request handle: {handle}")
    code, results = await _wait_request_response(bus, handle, timeout=timeout)
    if code != 0:
        raise RuntimeError(f"Portal returned error code {code}")
    return results

async def start_screencast_session(multiple: bool = True, cursor_mode: int = 2) -> Tuple[int, List[Dict[str, Any]], str]:
    """
    Returns: (pipewire_fd, streams, session_path)
      - pipewire_fd: int (dup() 済み FD。呼び出し側で close してOK)
      - streams: [{'node_id': int, 'object_path': str|None, 'position': (x,y)|None, 'size': (w,h)|None, 'source_type': int|None }, ...]
      - session_path: '/org/freedesktop/portal/desktop/session/...'
    """
    # ★ 重要: UNIX FD の交渉を有効化
    bus = await MessageBus(negotiate_unix_fd=True).connect()

    # Request 応答シグナルを確実に受け取る
    await _add_match(bus, "type='signal',sender='org.freedesktop.portal.Desktop',interface='org.freedesktop.portal.Request'")

    # ---- CreateSession ----
    tok  = f"ss2gd_{uuid.uuid4().hex[:8]}"
    stok = f"ss2gd_{uuid.uuid4().hex[:8]}_sess"
    if DEBUG: print("[portal] call ScreenCast.CreateSession")
    res = await _call_with_handle(
        bus, IF_SC, "CreateSession", "a{sv}",
        [{
            "handle_token":         Variant("s", tok),
            "session_handle_token": Variant("s", stok),
        }]
    )
    sess = _v(res.get("session_handle"))
    if not isinstance(sess, str):
        raise RuntimeError("ScreenCast.CreateSession returned no session_handle")
    session_path = sess

    # ---- SelectSources ----
    if DEBUG: print("[portal] call ScreenCast.SelectSources")
    sel_tok = f"ss2gd_{uuid.uuid4().hex[:8]}"
    await _call_with_handle(
        bus, IF_SC, "SelectSources", "oa{sv}",
        [session_path, {
            "handle_token": Variant("s", sel_tok),
            "types":        Variant("u", 1),                 # 1 = MONITOR
            "multiple":     Variant("b", bool(multiple)),
            "cursor_mode":  Variant("u", int(cursor_mode)),  # 2 = Embedded
        }]
    )

    # ---- Start ----
    if DEBUG: print("[portal] call ScreenCast.Start")
    start_tok = f"ss2gd_{uuid.uuid4().hex[:8]}"
    res2 = await _call_with_handle(
        bus, IF_SC, "Start", "osa{sv}",
        [session_path, "", {"handle_token": Variant("s", start_tok)}]
    )

    # streams: a(ua{sv}) or a(oa{sv})
    raw_streams = res2.get("streams")
    streams_py = _deep_unvariant(raw_streams)
    if DEBUG:
        print(f"[portal] raw streams (unvariant): {streams_py}")

    streams: List[Dict[str, Any]] = []
    if isinstance(streams_py, Sequence):
        for item in streams_py:
            if not (isinstance(item, (list, tuple)) and len(item) == 2):
                continue
            first, props = item[0], item[1] if isinstance(item[1], dict) else {}
            obj_path = None
            node_id = None

            if isinstance(first, int):
                node_id = first                   # a(ua{sv})
            elif isinstance(first, str):
                obj_path = first                   # a(oa{sv})
                node_id = props.get("node_id") or props.get("node-id") or props.get("pipewire_node_id")

            try:
                if node_id is not None:
                    node_id = int(node_id)
            except Exception:
                pass

            pos  = props.get("position")
            size = props.get("size")
            styp = props.get("source_type") or props.get("source-type")

            streams.append({
                "node_id": node_id,
                "object_path": obj_path,
                "position": tuple(pos)  if isinstance(pos,  (list, tuple)) and len(pos)==2 else None,
                "size":     tuple(size) if isinstance(size, (list, tuple)) and len(size)==2 else None,
                "source_type": int(styp) if isinstance(styp, int) else None,
            })

    if DEBUG:
        print(f"[portal] streams (parsed): {streams}")

    if not streams or streams[0].get("node_id") is None:
        raise RuntimeError("ScreenCast.Start: no usable node_id in streams")

    # ---- OpenPipeWireRemote ----
    if DEBUG: print("[portal] call ScreenCast.OpenPipeWireRemote")
    msg = Message(destination=PORTAL, path=OBJ, interface=IF_SC, member="OpenPipeWireRemote",
                  signature="oa{sv}", body=[session_path, {}])
    # 応答待ちで固まる環境への対策としてタイムアウト
    r = await asyncio.wait_for(bus.call(msg), timeout=10.0)

    if r.message_type != MessageType.METHOD_RETURN:
        raise RuntimeError(f"OpenPipeWireRemote failed: {r.error_name}")

    if not r.unix_fds:
        raise RuntimeError("OpenPipeWireRemote returned no fd")
    fd = os.dup(r.unix_fds[0])
    if DEBUG: print(f"[portal] got fd={fd}")

    return fd, streams, session_path
