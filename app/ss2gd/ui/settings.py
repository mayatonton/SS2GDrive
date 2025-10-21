from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox, QComboBox,
    QSpinBox, QPushButton, QFileDialog, QMessageBox, QApplication
)
import json, os, shutil, subprocess

from ..config import load_settings, save_settings, CLIENT_SECRET_PATH
from ..drive_uploader import is_authorized, sign_in


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SS2GDrive Settings")

        st = load_settings()
        lay = QVBoxLayout(self)

        # --- Google 認証 ---
        row0 = QHBoxLayout()
        self.lbl_auth = QLabel("Google Drive: 🟠 Not signed in")
        if is_authorized():
            self.lbl_auth.setText("Google Drive: ✅ Signed in")
        btn_auth = QPushButton("Sign in to Google…")
        btn_auth.clicked.connect(self.on_signin)
        row0.addWidget(self.lbl_auth); row0.addWidget(btn_auth)
        lay.addLayout(row0)

        # --- client_secret.json ---
        row0b = QHBoxLayout()
        self.lbl_secret = QLabel(self._secret_status_text())
        btn_secret = QPushButton("Import client_secret.json…")
        btn_secret.clicked.connect(self.on_import_secret)
        row0b.addWidget(self.lbl_secret); row0b.addWidget(btn_secret)
        lay.addLayout(row0b)

        # --- Drive フォルダ & 公開設定 ---
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Drive Folder ID:"))
        self.ed_folder = QLineEdit(st.get("upload_folder_id") or "")
        self.ed_folder.setPlaceholderText("(optional)")
        row1.addWidget(self.ed_folder)
        lay.addLayout(row1)

        self.cb_publish = QCheckBox("Anyone with the link can view")
        self.cb_publish.setChecked(bool(st.get("publish_anyone", True)))
        lay.addWidget(self.cb_publish)

        # --- 画像形式 & JPEG 品質 ---
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Image format:"))
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItems(["png", "jpeg"])
        self.cmb_fmt.setCurrentText(st.get("image_format", "png"))
        row2.addWidget(self.cmb_fmt)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("JPEG quality:"))
        self.sp_qual = QSpinBox()
        self.sp_qual.setRange(50, 100)
        self.sp_qual.setValue(int(st.get("jpeg_quality", 90)))
        row3.addWidget(self.sp_qual)
        lay.addLayout(row3)

        # --- 音声入力 ---
        rowA = QHBoxLayout()
        rowA.addWidget(QLabel("Audio input:"))
        self.cmb_audio_mode = QComboBox()
        self.cmb_audio_mode.addItem("System audio (auto)", "auto")
        self.cmb_audio_mode.addItem("None", "none")
        self.cmb_audio_mode.addItem("Choose device…", "device")
        rowA.addWidget(self.cmb_audio_mode)
        lay.addLayout(rowA)

        rowB = QHBoxLayout()
        rowB.addWidget(QLabel("Device:"))
        self.cmb_audio_dev = QComboBox()
        self.btn_audio_refresh = QPushButton("Refresh")
        self.btn_audio_refresh.clicked.connect(self.on_refresh_devices)
        rowB.addWidget(self.cmb_audio_dev)
        rowB.addWidget(self.btn_audio_refresh)
        lay.addLayout(rowB)

        self.cmb_audio_mode.currentIndexChanged.connect(self.on_audio_mode_changed)

        # 初期反映
        self._init_audio_from_settings(st)

        # --- OK/Cancel ---
        btns = QHBoxLayout()
        ok = QPushButton("Save")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        lay.addLayout(btns)

    # ========= Google auth =========
    def on_signin(self):
        try:
            if sign_in(interactive=True):
                self.lbl_auth.setText("Google Drive: ✅ Signed in")
        except Exception as e:
            QMessageBox.critical(self, "Sign in failed", str(e))

    def on_import_secret(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select client_secret.json", os.path.expanduser("~"),
            "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not ("installed" in data or "web" in data):
                raise ValueError("Not a valid Google OAuth client JSON")
        except Exception as e:
            QMessageBox.critical(self, "Invalid file", f"{e}")
            return
        os.makedirs(os.path.dirname(CLIENT_SECRET_PATH), exist_ok=True)
        try:
            shutil.copyfile(path, CLIENT_SECRET_PATH)
        except Exception as e:
            QMessageBox.critical(self, "Copy failed", str(e))
            return
        self.lbl_secret.setText(self._secret_status_text())
        QMessageBox.information(self, "Imported", f"Saved to:\n{CLIENT_SECRET_PATH}")

    def _secret_status_text(self) -> str:
        return (f"client_secret.json: ✅ Found ({CLIENT_SECRET_PATH})"
                if os.path.exists(CLIENT_SECRET_PATH)
                else "client_secret.json: 🟠 Not found (will prompt on Sign in)")

    # ========= Audio UI helpers =========
    def _monitor_sources(self) -> list[str]:
        """*.monitor を列挙。失敗時は空配列"""
        try:
            r = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, check=False
            )
            out = []
            for ln in r.stdout.splitlines():
                cols = ln.split()
                if len(cols) >= 2 and ".monitor" in cols[1]:
                    out.append(cols[1])
            return out
        except Exception:
            return []

    def on_refresh_devices(self):
        want = self.cmb_audio_dev.currentData() or self.cmb_audio_dev.currentText()
        devices = self._monitor_sources()

        self.cmb_audio_dev.clear()
        if not devices:
            # 表示のみ（保存時にこのまま書かないよう itemData は None にしておく）
            self.cmb_audio_dev.addItem("(no monitor devices found)", None)
            self.cmb_audio_dev.setEnabled(False)
            self.btn_audio_refresh.setEnabled(True)
            return

        # 表示テキスト＝デバイス名、itemData にも同じ値を入れる（テキストとデータを一致）
        for dev in devices:
            self.cmb_audio_dev.addItem(dev, dev)

        self.cmb_audio_dev.setEnabled(True)
        self.btn_audio_refresh.setEnabled(True)

        # 以前の選択があれば復元（itemData 優先で一致させる）
        if want:
            for i in range(self.cmb_audio_dev.count()):
                if self.cmb_audio_dev.itemData(i) == want:
                    self.cmb_audio_dev.setCurrentIndex(i)
                    break

    def on_audio_mode_changed(self, _idx: int):
        mode = self.cmb_audio_mode.currentData()
        is_dev = (mode == "device")
        self.cmb_audio_dev.setEnabled(is_dev)
        self.btn_audio_refresh.setEnabled(is_dev)
        if is_dev and self.cmb_audio_dev.count() == 0:
            self.on_refresh_devices()

    def _init_audio_from_settings(self, st: dict):
        audio = st.get("audio") or {}
        mode = audio.get("mode", "auto")
        # モード反映
        idx = 0
        for i in range(self.cmb_audio_mode.count()):
            if self.cmb_audio_mode.itemData(i) == mode:
                idx = i
                break
        self.cmb_audio_mode.setCurrentIndex(idx)

        # デバイス一覧を読んで選択
        self.on_refresh_devices()
        if mode == "device":
            want = (audio.get("device") or "").strip()
            if want:
                for i in range(self.cmb_audio_dev.count()):
                    if self.cmb_audio_dev.itemData(i) == want:
                        self.cmb_audio_dev.setCurrentIndex(i)
                        break
        self.on_audio_mode_changed(self.cmb_audio_mode.currentIndex())

    # ========= Save / Values =========
    def get_values(self) -> dict:
        d = {
            "upload_folder_id": self.ed_folder.text().strip() or None,
            "publish_anyone": self.cb_publish.isChecked(),
            "image_format": self.cmb_fmt.currentText(),
            "jpeg_quality": self.sp_qual.value(),
        }
        # 音声設定は itemData（＝内部値）を優先して保存
        mode = self.cmb_audio_mode.currentData()
        audio = {"mode": mode}
        if mode == "device":
            dev = self.cmb_audio_dev.currentData() or self.cmb_audio_dev.currentText().strip()
            if dev and not dev.startswith("("):
                audio["device"] = dev
        d["audio"] = audio
        return d

    def accept(self):
        cur = load_settings()  # マージ保存（未知キー温存）
        cur.update(self.get_values())
        save_settings(cur)
        super().accept()
