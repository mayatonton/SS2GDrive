# app/ss2gd/config.py
from __future__ import annotations
import os, json
from pathlib import Path

APP_ID = "com.ss2gd.SS2GDrive"

def _config_root() -> Path:
    """
    Flatpak では XDG_CONFIG_HOME が
      ~/.var/app/com.ss2gd.SS2GDrive/config
    に設定される。無ければ通常の ~/.config を使う。
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    # 念のため Flatpak の既定パスも見る
    flatpak_cfg = Path.home() / ".var/app" / APP_ID / "config"
    return flatpak_cfg if flatpak_cfg.exists() else (Path.home() / ".config")

CFG_DIR = _config_root() / "ss2gdrive"
CFG_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH      = CFG_DIR / "settings.json"
CLIENT_SECRET_PATH = CFG_DIR / "client_secret.json"
TOKEN_PATH         = CFG_DIR / "token.json"

def load_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_settings(d: dict) -> None:
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)

def ensure_videos_dir() -> str:
    p = Path.home() / "Videos" / "SS2GDrive"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)

def load_embedded_client_config() -> dict | None:
    """
    将来的に Flatpak にクライアント JSON を同梱する場合用。
    今は None を返して通常パスを使わせる。
    """
    return None
