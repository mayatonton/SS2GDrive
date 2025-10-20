from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QCheckBox,QComboBox,QSpinBox,QPushButton,QFileDialog,QMessageBox, QApplication)
import json, os, shutil
from ..config import load_settings, save_settings, CLIENT_SECRET_PATH
from ..drive_uploader import is_authorized, sign_in
class SettingsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("SS2GDrive Settings"); st=load_settings(); lay=QVBoxLayout(self)
        row0=QHBoxLayout(); self.lbl_auth=QLabel("Google Drive: 🟠 Not signed in")
        if is_authorized(): self.lbl_auth.setText("Google Drive: ✅ Signed in")
        btn_auth=QPushButton("Sign in to Google…"); btn_auth.clicked.connect(self.on_signin); row0.addWidget(self.lbl_auth); row0.addWidget(btn_auth); lay.addLayout(row0)
        row0b=QHBoxLayout(); self.lbl_secret=QLabel(self._secret_status_text()); btn_secret=QPushButton("Import client_secret.json…"); btn_secret.clicked.connect(self.on_import_secret); row0b.addWidget(self.lbl_secret); row0b.addWidget(btn_secret); lay.addLayout(row0b)
        row1=QHBoxLayout(); row1.addWidget(QLabel("Drive Folder ID:")); self.ed_folder=QLineEdit(st.get("upload_folder_id") or ""); self.ed_folder.setPlaceholderText("(optional)"); row1.addWidget(self.ed_folder); lay.addLayout(row1)
        self.cb_publish=QCheckBox("Anyone with the link can view"); self.cb_publish.setChecked(bool(st.get("publish_anyone", True))); lay.addWidget(self.cb_publish)
        row2=QHBoxLayout(); row2.addWidget(QLabel("Image format:")); self.cmb_fmt=QComboBox(); self.cmb_fmt.addItems(["png","jpeg"]); self.cmb_fmt.setCurrentText(st.get("image_format","png")); row2.addWidget(self.cmb_fmt); lay.addLayout(row2)
        row3=QHBoxLayout(); row3.addWidget(QLabel("JPEG quality:")); self.sp_qual=QSpinBox(); self.sp_qual.setRange(50,100); self.sp_qual.setValue(int(st.get("jpeg_quality",90))); row3.addWidget(self.sp_qual); lay.addLayout(row3)
        btns=QHBoxLayout(); ok=QPushButton("Save"); cancel=QPushButton("Cancel"); ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject); btns.addWidget(ok); btns.addWidget(cancel); lay.addLayout(btns)
    def on_signin(self):
        try:
            if sign_in(interactive=True): self.lbl_auth.setText("Google Drive: ✅ Signed in")
        except Exception as e: QMessageBox.critical(self,"Sign in failed",str(e))
    def on_import_secret(self):
        path,_=QFileDialog.getOpenFileName(self,"Select client_secret.json",os.path.expanduser("~"),"JSON Files (*.json);;All Files (*)")
        if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f: data=json.load(f)
            if not isinstance(data,dict) or not ("installed" in data or "web" in data): raise ValueError("Not a valid Google OAuth client JSON")
        except Exception as e: QMessageBox.critical(self,"Invalid file",f"{e}"); return
        os.makedirs(os.path.dirname(CLIENT_SECRET_PATH), exist_ok=True)
        try: shutil.copyfile(path, CLIENT_SECRET_PATH)
        except Exception as e: QMessageBox.critical(self,"Copy failed",str(e)); return
        self.lbl_secret.setText(self._secret_status_text()); QMessageBox.information(self,"Imported",f"Saved to:\n{CLIENT_SECRET_PATH}")
    def _secret_status_text(self)->str:
        import os
        return (f"client_secret.json: ✅ Found ({CLIENT_SECRET_PATH})" if os.path.exists(CLIENT_SECRET_PATH) else "client_secret.json: 🟠 Not found (will prompt on Sign in)")
    def get_values(self)->dict:
        return {"upload_folder_id": self.ed_folder.text().strip() or None, "publish_anyone": self.cb_publish.isChecked(), "image_format": self.cmb_fmt.currentText(), "jpeg_quality": self.sp_qual.value()}
    def accept(self):
        save_settings(self.get_values()); super().accept()
