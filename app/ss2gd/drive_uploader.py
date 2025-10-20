import os
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .config import CLIENT_SECRET_PATH, TOKEN_PATH, load_settings, load_embedded_client_config
SCOPES=["https://www.googleapis.com/auth/drive.file"]
def _load_creds()->Optional[Credentials]:
    if os.path.exists(TOKEN_PATH):
        try: return Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception: return None
    return None
def _save_creds(creds:Credentials)->None:
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH,"w") as f: f.write(creds.to_json())
def sign_in(interactive:bool=True)->bool:
    creds=_load_creds()
    if creds and creds.valid: return True
    if creds and creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        try: creds.refresh(Request()); _save_creds(creds); return True
        except Exception: pass
    cfg=load_embedded_client_config()
    if cfg:
        flow=InstalledAppFlow.from_client_config(cfg, SCOPES)
        creds=flow.run_local_server(open_browser=True, port=0); _save_creds(creds); return True
    if not os.path.exists(CLIENT_SECRET_PATH):
        raise FileNotFoundError(f"client_secret.json not found at {CLIENT_SECRET_PATH}")
    flow=InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds=flow.run_local_server(open_browser=True, port=0); _save_creds(creds); return True
def is_authorized()->bool:
    c=_load_creds(); return bool(c and c.valid)
def _service():
    creds=_load_creds()
    if not (creds and creds.valid):
        sign_in(interactive=True); creds=_load_creds()
    return build("drive","v3", credentials=creds)
def upload_and_share(filepath:str, mime_type="image/png", description="captured by SS2GDrive"):
    st=load_settings(); folder_id=st.get("upload_folder_id"); publish=bool(st.get("publish_anyone", True))
    svc=_service()
    body={"name": os.path.basename(filepath), "description": description, "appProperties":{"uploader":"SS2GDrive"}}
    if folder_id: body["parents"]=[folder_id]
    media=MediaFileUpload(filepath, mimetype=mime_type, chunksize=8*1024*1024, resumable=True)
    req=svc.files().create(body=body, media_body=media, fields="id,webViewLink", supportsAllDrives=True)
    resp=None
    while resp is None:
        status, resp=req.next_chunk()
    file_id=resp["id"]
    if publish: svc.permissions().create(fileId=file_id, body={"type":"anyone","role":"reader"}).execute()
    fin=svc.files().get(fileId=file_id, fields="webViewLink", supportsAllDrives=True).execute()
    link=fin["webViewLink"]
    return link
