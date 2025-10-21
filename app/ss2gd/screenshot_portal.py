# app/ss2gd/screenshot_portal.py
import os, asyncio, time, shutil
from typing import Any, Dict, Tuple
from urllib.parse import urlparse, unquote

from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, Variant

PORTAL  = "org.freedesktop.portal.Desktop"
OBJ     = "/org/freedesktop/portal/desktop"
IF_SS   = "org.freedesktop.portal.Screenshot"
IF_REQ  = "org.freedesktop.portal.Request"

DEBUG = bool(os.environ.get("SS2GD_DEBUG"))
DEFAULT_TIMEOUT = float(os.environ.get("SS2GD_SS_TIMEOUT", "60"))

class PortalError(Exception):
    pass

def _v(x):
    return x.value if isinstance(x, Variant) else x

async def _add_match(bus: MessageBus, rule: str) -> None:
    if DEBUG:
        print(f"[dbus] AddMatch: {rule}")
    msg = Message(
        destination="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface="org.freedesktop.DBus",
        member="AddMatch",
        signature="s",
        body=[rule],
    )
    await bus.call(msg)

async def _wait_request_response(bus: MessageBus, handle: str, timeout: float) -> Tuple[int, Dict[str, Any]]:
    fut: asyncio.Future = asyncio.get_running_loop().create_future()

    def handler(msg):
        if (
            msg.message_type == MessageType.SIGNAL
            and msg.interface == IF_REQ
            and msg.member == "Response"
            and msg.path == handle
        ):
            code = msg.body[0]
            results = msg.body[1] if len(msg.body) > 1 else {}
            if DEBUG:
                print(f"[portal] response code={code}, keys={list(results.keys())}")
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

async def _call_with_handle(bus: MessageBus, interface: str, member: str, signature: str, body: list, timeout: float):
    msg = Message(destination=PORTAL, path=OBJ, interface=interface, member=member, signature=signature, body=body)
    reply = await bus.call(msg)
    if reply.message_type != MessageType.METHOD_RETURN:
        raise PortalError(reply.error_name)
    handle = reply.body[0]  # Request object path
    if DEBUG:
        print(f"[portal] request handle: {handle}")
    code, results = await _wait_request_response(bus, handle, timeout=timeout)
    if code != 0:
        raise PortalError("Screenshot canceled or denied by portal")
    return results

async def _do_screenshot() -> str:
    """
    戻り: ドキュメントポータルURI (file:///run/user/.../doc/.../Screenshot ...)
    実装差吸収のため、まず 'sa{sv}'（parent_window + options）を試し、InvalidArgs なら 'a{sv}' にフォールバック。
    """
    bus = await MessageBus().connect()
    await _add_match(bus, "type='signal',sender='org.freedesktop.portal.Desktop',interface='org.freedesktop.portal.Request'")

    token = f"ss2gd_{os.getpid()}_{int(time.time())}"
    opts = {
        "handle_token": Variant("s", token),
        "interactive":  Variant("b", True),
        # "modal": Variant("b", True),  # 必要なら有効化
    }

    # 1) 推奨：parent_window を空文字で渡す ('sa{sv}')
    if DEBUG:
        print("[portal] call Screenshot.Screenshot (sa{sv})")
    try:
        res = await _call_with_handle(bus, IF_SS, "Screenshot", "sa{sv}", ["", opts], timeout=DEFAULT_TIMEOUT)
    except PortalError as e:
        if "InvalidArgs" not in str(e):
            raise
        # 2) 旧挙動：options のみ ('a{sv}')
        if DEBUG:
            print("[portal] call Screenshot.Screenshot (a{sv}) fallback")
        res = await _call_with_handle(bus, IF_SS, "Screenshot", "a{sv}", [opts], timeout=DEFAULT_TIMEOUT)

    uri = _v(res.get("uri"))
    if DEBUG:
        print(f"[portal] uri: {uri!r}")
    if not uri or not isinstance(uri, str):
        raise PortalError("Portal returned no uri")
    return uri

async def _copy_from_doc_portal_uri(uri: str) -> str:
    """
    /run/user/.../doc/... のファイルを /tmp にコピーしてローカルパスを返す。
    Portal 側の出現遅延に備え、短時間ポーリング。
    """
    path = unquote(urlparse(uri).path)
    dst  = os.path.join("/tmp", f"ss2gd-{os.getpid()}-{int(time.time())}.png")

    # 0.1s × 最大40回（~4秒）待つ
    for i in range(40):
        try:
            shutil.copyfile(path, dst)
            if DEBUG:
                print(f"[portal] copied: {path} -> {dst}")
            return dst
        except FileNotFoundError:
            if DEBUG:
                print(f"[portal] wait for file... {i}")
            await asyncio.sleep(0.1)
        except Exception as e:
            if DEBUG:
                print(f"[portal] copy failed: {e!r}")
            await asyncio.sleep(0.1)

    raise PortalError("Screenshot file not available")

async def take_interactive_screenshot_async() -> str:
    """インタラクティブな矩形選択 → 一時PNGパスを返す（/tmp 配下）"""
    uri = await _do_screenshot()
    return await _copy_from_doc_portal_uri(uri)

def take_interactive_screenshot() -> str:
    """同期版（CLI 等から直接呼べるエントリ）"""
    return asyncio.run(take_interactive_screenshot_async())

__all__ = ["take_interactive_screenshot", "PortalError"]
