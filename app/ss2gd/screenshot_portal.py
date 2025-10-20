import asyncio, os, tempfile, urllib.parse
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, Variant

PORTAL_BUS = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
SCREENSHOT_IFACE = 'org.freedesktop.portal.Screenshot'
REQUEST_IFACE = 'org.freedesktop.portal.Request'
DEFAULT_TIMEOUT = int(os.environ.get("SS2GD_TIMEOUT", "25"))

class PortalError(RuntimeError): pass

def _uri_to_path(uri: str) -> str:
    if not uri.startswith('file://'):
        raise PortalError(f'Portal returned unexpected uri: {uri!r}')
    return urllib.parse.unquote(uri[len('file://'):])

async def _add_match(bus: MessageBus, rule: str):
    msg = Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus',
                  interface='org.freedesktop.DBus', member='AddMatch', signature='s', body=[rule])
    reply = await bus.call(msg)
    if reply.message_type == MessageType.ERROR:
        raise PortalError(f'AddMatch failed: {reply.error_name}')

async def _remove_match(bus: MessageBus, rule: str):
    msg = Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus',
                  interface='org.freedesktop.DBus', member='RemoveMatch', signature='s', body=[rule])
    try: await bus.call(msg)
    except Exception: pass

async def _call_screenshot_interactive() -> str:
    bus = await MessageBus().connect()

    token = os.urandom(8).hex()
    opts = {'interactive': Variant('b', True), 'handle_token': Variant('s', token)}

    msg = Message(destination=PORTAL_BUS, path=PORTAL_PATH, interface=SCREENSHOT_IFACE,
                  member='Screenshot', signature='sa{sv}', body=['', opts])

    reply = await bus.call(msg)
    if reply.message_type == MessageType.ERROR:
        raise PortalError(f'Portal call failed: {reply.error_name}')

    handle_path = reply.body[0]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    def on_signal(m):
        if m.path != handle_path or m.interface != REQUEST_IFACE or m.member != 'Response':
            return
        code, results = m.body
        if code != 0:
            fut.set_exception(PortalError('Screenshot canceled or denied by portal')); return
        uri = results.get('uri')
        if isinstance(uri, Variant): uri = uri.value
        try: p = _uri_to_path(uri)
        except Exception as e: fut.set_exception(e); return
        fut.set_result(p)

    bus.add_message_handler(on_signal)
    rule = (f"type='signal',sender='{PORTAL_BUS}',path='{handle_path}',"
            f"interface='{REQUEST_IFACE}',member='Response'")
    await _add_match(bus, rule)

    try:
        path = await asyncio.wait_for(fut, timeout=DEFAULT_TIMEOUT)
    finally:
        try: await _remove_match(bus, rule)
        except Exception: pass
        try: bus.remove_message_handler(on_signal)
        except Exception: pass
        try: bus.disconnect()
        except Exception: pass
    return path

async def take_interactive_screenshot() -> str:
    src = await _call_screenshot_interactive()
    suffix = os.path.splitext(src)[1] or '.png'
    fd, dst = tempfile.mkstemp(prefix='ss2gd-', suffix=suffix)
    os.close(fd)
    with open(src, 'rb') as r, open(dst, 'wb') as w:
        w.write(r.read())
    return dst
