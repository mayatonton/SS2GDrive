import os, json
APP_ID = "com.ss2gd.SS2GDrive"
_DEF = {"publish_anyone": True, "upload_folder_id": None, "image_format": "png", "jpeg_quality": 90, "open_in_browser": True}
def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, "SS2GDrive"); os.makedirs(path, exist_ok=True); return path
CLIENT_SECRET_PATH = os.path.join(config_dir(), "client_secret.json")
TOKEN_PATH = os.path.join(config_dir(), "token.json")
SETTINGS_PATH = os.path.join(config_dir(), "settings.json")
PID_PATH = os.path.join(config_dir(), "tray.pid")
EMBEDDED_CLIENT_PATH = os.path.join(os.path.dirname(__file__), "embedded_client.json")
def load_settings()->dict:
    d=_DEF.copy()
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH,"r",encoding="utf-8") as f: d.update(json.load(f))
    except Exception: pass
    return d
def save_settings(v:dict):
    d=_DEF.copy(); d.update(v)
    with open(SETTINGS_PATH,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
def load_embedded_client_config():
    cid=os.environ.get("SS2GD_CLIENT_ID"); cs=os.environ.get("SS2GD_CLIENT_SECRET")
    if cid and cs:
        return {"installed":{"client_id":cid,"client_secret":cs,"redirect_uris":["http://localhost","http://localhost:8080/","http://localhost:8090/"],"auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}}
    if os.path.exists(EMBEDDED_CLIENT_PATH):
        try:
            import json as _json
            with open(EMBEDDED_CLIENT_PATH,"r",encoding="utf-8") as f:
                data=_json.load(f)
                if isinstance(data,dict) and ("installed" in data or "web" in data): return data
        except Exception: pass
    return None
