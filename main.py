import sys
from pathlib import Path
from datetime import datetime
import re
import requests
from PySide6 import QtCore, QtGui, QtWidgets

import services as svc

APP_NAME = "MCSHoster"

def info_button(text: str, parent: QtWidgets.QWidget) -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton()
    btn.setText("?")
    btn.setObjectName("infoBtn")
    btn.setToolTip(text)
    btn.setFixedSize(20, 20)
    btn.clicked.connect(lambda: QtWidgets.QMessageBox.information(parent, "Info", text))
    return btn

class SetupTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state

        # Server directory
        self.dir_edit = QtWidgets.QLineEdit(str(self.state["server_dir"]))
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_dir)

        # Server type
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(svc.SERVER_TYPES)

        # Versions (Vanilla only)
        self.version_combo = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton("Refresh versions")

        # Download / upload jar
        self.download_btn = QtWidgets.QPushButton("Download selected version (Vanilla)")

        self.upload_server_btn = QtWidgets.QPushButton("Upload custom server.jar")

        # Bootstrap & EULA
        self.bootstrap_btn = QtWidgets.QPushButton("Bootstrap server (generate files)")

        self.eula_checkbox = QtWidgets.QCheckBox("Accept EULA")

        # Status / logs
        self.status = QtWidgets.QPlainTextEdit()
        self.status.setReadOnly(True)

        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        self.refresh_btn.clicked.connect(self.load_versions)
        self.download_btn.clicked.connect(self.download_version)
        self.upload_server_btn.clicked.connect(self.upload_custom_jar)
        self.bootstrap_btn.clicked.connect(self.bootstrap_server)
        self.eula_checkbox.stateChanged.connect(self.toggle_eula)

        form = QtWidgets.QFormLayout(self)
        form.addRow("Server directory:", self.row_with(self.dir_edit, browse_btn, info_button("Where server.jar and world files will live.", self)))
        form.addRow("Server type:", self.row_with(self.type_combo, info_button("Choose Vanilla (no plugins) or a plugin-capable jar (Paper/Spigot/Purpur) or Custom.", self)))
        form.addRow("Version (Vanilla):", self.row_with(self.version_combo, self.refresh_btn))
        form.addRow(self.row_with(self.download_btn, self.upload_server_btn))
        form.addRow(self.row_with(self.bootstrap_btn, info_button("Runs the jar once to generate eula.txt and server.properties.", self)))
        form.addRow(self.eula_checkbox)
        form.addRow("Status:", self.status)

        self.load_versions()
        self.on_type_changed(self.type_combo.currentText())

    def row_with(self, *widgets):
        h = QtWidgets.QHBoxLayout()
        w = QtWidgets.QWidget()
        for wd in widgets:
            h.addWidget(wd)
        h.addStretch()
        w.setLayout(h)
        return w

    def browse_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose server directory", str(self.state["server_dir"]))
        if d:
            self.state["server_dir"] = Path(d)
            self.dir_edit.setText(d)
            self.log("Server directory set.")

    def on_type_changed(self, t: str):
        self.version_combo.setEnabled(t == "Vanilla")
        self.refresh_btn.setEnabled(t == "Vanilla")
        self.download_btn.setEnabled(t == "Vanilla")
        self.upload_server_btn.setEnabled(True)
        self.log(f"Server type: {t}")

    def load_versions(self):
        self.version_combo.clear()
        self.version_combo.addItem("Loading versions...")
        self.refresh_btn.setEnabled(False)
        
        try:
            versions = svc.get_versions()
            self.version_combo.clear()
            
            if not versions:
                self.version_combo.addItem("No versions available")
                self.log("No versions found from Mojang.")
                return
            
            releases = [v for v in versions if v.get("type") == "release"]
            snapshots = [v for v in versions if v.get("type") == "snapshot"]
            
            for v in releases[:60]:
                self.version_combo.addItem(f"{v['id']} (release)", v["id"])
            for v in snapshots[:20]:
                self.version_combo.addItem(f"{v['id']} (snapshot)", v["id"])
            
            self.log(f"Loaded {len(releases)} releases and {len(snapshots)} snapshots.")
        except requests.exceptions.ConnectionError:
            self.version_combo.clear()
            self.version_combo.addItem("Connection error")
            self.log("Failed to load versions: No internet connection.")
        except requests.exceptions.Timeout:
            self.version_combo.clear()
            self.version_combo.addItem("Timeout")
            self.log("Failed to load versions: Request timed out.")
        except Exception as e:
            self.version_combo.clear()
            self.version_combo.addItem("Error loading versions")
            self.log(f"Failed to load versions: {e}")
        finally:
            self.refresh_btn.setEnabled(True)

    def download_version(self):
        vid = self.version_combo.currentData()
        try:
            svc.download_server_jar(self.state["server_dir"], vid)
            self.log(f"Downloaded server.jar for {vid}.")
        except Exception as e:
            self.log(f"Download failed: {e}")

    def upload_custom_jar(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select server jar", "", "Jar Files (*.jar)")
        if f:
            try:
                svc.place_custom_server_jar(self.state["server_dir"], Path(f))
                self.log("Custom server.jar placed.")
            except Exception as e:
                self.log(f"Upload failed: {e}")

    def bootstrap_server(self):
        if not self.eula_checkbox.isChecked():
            QtWidgets.QMessageBox.warning(self, "EULA Required", "You must check the 'Accept EULA' box before bootstrapping the server.")
            return
        # Explicitly set EULA to true before running, to avoid race conditions.
        svc.set_eula(self.state["server_dir"], True)
        self.log("EULA set to true. Starting bootstrap...")
        ok, out = svc.bootstrap_server(self.state["server_dir"], self.state.get("java_args"))
        self.log(out.strip() or "(no output)")
        self.log("Bootstrap complete." if ok else "Bootstrap failed or timed out.")

    def toggle_eula(self, state):
        self.log(f"EULA checkbox {'checked' if state == QtCore.Qt.Checked else 'unchecked'}.")

    def log(self, msg: str):
        self.status.appendPlainText(msg)
        svc.log(self.state["server_dir"], msg)

class SettingsTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.props = {}
        self.controls = {}
        self.refresh_btn = QtWidgets.QPushButton("Load settings")
        self.save_btn = QtWidgets.QPushButton("Save settings")
        self.refresh_btn.clicked.connect(self.load_props)
        self.save_btn.clicked.connect(self.save_props)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)
        main_layout = QtWidgets.QVBoxLayout(self); main_layout.addWidget(scroll_area)

        def add(k, widget, help_text=""):
            self.controls[k] = widget
            h_layout = QtWidgets.QHBoxLayout()
            h_layout.addWidget(widget)
            if help_text:
                h_layout.addWidget(info_button(help_text, self))
            h_layout.addStretch()
            wrap = QtWidgets.QWidget()
            wrap.setLayout(h_layout)
            label = k.replace("-", " ").replace(".", " ").title()
            form.addRow(label + ":", wrap)

        add("motd", QtWidgets.QLineEdit(), "Message shown in server list.")
        add("difficulty", self.combo(["peaceful", "easy", "normal", "hard"]), "Game difficulty.")
        add("pvp", self.bool_combo(), "Allow player vs player combat.")
        add("online-mode", self.bool_combo(), "true = use Mojang auth; false = offline (not recommended).")
        add("white-list", self.bool_combo(), "Restrict joining to whitelist.json entries.")
        add("allow-flight", self.bool_combo(), "Allow flight (useful for some mods/plugins).")
        add("spawn-protection", self.spin(0, 1024), "Radius around spawn where non-ops cannot build.")
        add("max-players", self.spin(1, 1000), "Max players allowed simultaneously.")
        add("view-distance", self.spin(2, 32), "Chunks sent to clients around player.")
        add("simulation-distance", self.spin(2, 32), "Chunks with game logic active.")
        add("level-seed", QtWidgets.QLineEdit(), "Seed for world generation.")
        add("level-name", QtWidgets.QLineEdit(), "Folder name for world.")
        add("enable-command-block", self.bool_combo(), "Enable command blocks.")
        add("server-port", self.spin(1, 65535), "Inbound TCP port for the server.")
        add("server-ip", QtWidgets.QLineEdit(), "Bind IP (usually leave empty).")
        add("enforce-secure-profile", self.bool_combo(), "Extra identity checks; can prevent cracked clients.")
        add("require-resource-pack", self.bool_combo(), "Force clients to accept resource pack.")
        add("resource-pack", QtWidgets.QLineEdit(), "URL to resource pack.")
        add("resource-pack-sha1", QtWidgets.QLineEdit(), "SHA1 checksum of pack.")
        add("enable-status", self.bool_combo(), "Allow server status pings.")
        add("enable-jmx-monitoring", self.bool_combo(), "Expose JMX metrics (advanced).")
        add("enable-rcon", self.bool_combo(), "Remote console protocol.")
        add("rcon.port", self.spin(1, 65535), "RCON TCP port.")
        add("rcon.password", QtWidgets.QLineEdit(), "RCON password.")
        add("enable-query", self.bool_combo(), "Legacy query protocol.")
        add("query.port", self.spin(1, 65535), "Query UDP port.")

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.save_btn)
        form.addRow(btns)
        self.load_props()

    def combo(self, items):
        cb = QtWidgets.QComboBox()
        for i in items: cb.addItem(i)
        return cb

    def bool_combo(self):
        cb = QtWidgets.QComboBox()
        cb.addItem("true"); cb.addItem("false")
        return cb

    def spin(self, mn, mx):
        s = QtWidgets.QSpinBox()
        s.setRange(mn, mx)
        return s

    def load_props(self):
        path = self.state["server_dir"] / "server.properties"
        self.props = svc.read_properties(path)
        for k, w in self.controls.items():
            v = self.props.get(k, "")
            if isinstance(w, QtWidgets.QLineEdit):
                w.setText(v)
            elif isinstance(w, QtWidgets.QSpinBox):
                try: w.setValue(int(v))
                except: w.setValue(w.minimum())
            elif isinstance(w, QtWidgets.QComboBox):
                idx = w.findText(v)
                w.setCurrentIndex(idx if idx >= 0 else 0)

    def save_props(self):
        for k, w in self.controls.items():
            if isinstance(w, QtWidgets.QLineEdit):
                self.props[k] = w.text().strip()
            elif isinstance(w, QtWidgets.QSpinBox):
                self.props[k] = str(w.value())
            elif isinstance(w, QtWidgets.QComboBox):
                self.props[k] = w.currentText()
        path = self.state["server_dir"] / "server.properties"
        try:
            svc.write_properties(path, self.props)
            QtWidgets.QMessageBox.information(self, "Saved", "server.properties updated.")
            svc.log(self.state["server_dir"], "Settings saved.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
            svc.log(self.state["server_dir"], f"Failed to save settings: {e}")

class UsersTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.ops_list = QtWidgets.QListWidget()
        self.op_name = QtWidgets.QLineEdit()
        self.op_uuid = QtWidgets.QLineEdit()
        self.op_add = QtWidgets.QPushButton("Add OP")
        self.op_remove = QtWidgets.QPushButton("Remove selected OP")
        self.op_add.clicked.connect(self.add_op)
        self.op_remove.clicked.connect(self.remove_op)

        self.wl_list = QtWidgets.QListWidget()
        self.wl_name = QtWidgets.QLineEdit()
        self.wl_uuid = QtWidgets.QLineEdit()
        self.wl_add = QtWidgets.QPushButton("Add to whitelist")
        self.wl_remove = QtWidgets.QPushButton("Remove selected")
        self.wl_add.clicked.connect(self.add_wl)
        self.wl_remove.clicked.connect(self.remove_wl)

        refresh_btn = QtWidgets.QPushButton("Refresh lists")
        refresh_btn.clicked.connect(self.refresh_lists)

        ops_box = QtWidgets.QGroupBox("Ops")
        ops_layout = QtWidgets.QGridLayout()
        ops_layout.addWidget(self.ops_list, 0, 0, 1, 2)
        ops_layout.addWidget(QtWidgets.QLabel("Name:"), 1, 0); ops_layout.addWidget(self.op_name, 1, 1)
        ops_layout.addWidget(QtWidgets.QLabel("UUID (optional):"), 2, 0); ops_layout.addWidget(self.op_uuid, 2, 1)
        ops_layout.addWidget(self.op_add, 3, 0); ops_layout.addWidget(self.op_remove, 3, 1)
        ops_box.setLayout(ops_layout)

        wl_box = QtWidgets.QGroupBox("Whitelist")
        wl_layout = QtWidgets.QGridLayout()
        wl_layout.addWidget(self.wl_list, 0, 0, 1, 2)
        wl_layout.addWidget(QtWidgets.QLabel("Name:"), 1, 0); wl_layout.addWidget(self.wl_name, 1, 1)
        wl_layout.addWidget(QtWidgets.QLabel("UUID (optional):"), 2, 0); wl_layout.addWidget(self.wl_uuid, 2, 1)
        wl_layout.addWidget(self.wl_add, 3, 0); wl_layout.addWidget(self.wl_remove, 3, 1)
        wl_box.setLayout(wl_layout)

        main_layout = QtWidgets.QVBoxLayout(self)
        h_layout = QtWidgets.QHBoxLayout()
        h_layout.addWidget(ops_box)
        h_layout.addWidget(wl_box)
        main_layout.addLayout(h_layout)
        main_layout.addWidget(refresh_btn)

        self.refresh_lists()

    def refresh_lists(self):
        self.ops_list.clear()
        ops = svc.read_json(self.state["server_dir"] / "ops.json", [])
        for e in ops:
            self.ops_list.addItem(f"{e.get('name')} ({e.get('uuid','no-uuid')})")
        self.wl_list.clear()
        wl = svc.read_json(self.state["server_dir"] / "whitelist.json", [])
        for e in wl:
            self.wl_list.addItem(f"{e.get('name')} ({e.get('uuid','no-uuid')})")

    def add_op(self):
        name = self.op_name.text().strip()
        uuid = self.op_uuid.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing", "Enter a player name.")
            return
        if uuid and not svc.validate_uuid(uuid):
            QtWidgets.QMessageBox.warning(self, "Invalid UUID", "Enter a valid UUID or leave empty.")
            return
        svc.add_op(self.state["server_dir"], name, uuid or None)
        self.refresh_lists()

    def remove_op(self):
        item = self.ops_list.currentItem()
        if item:
            name = item.text().split(" (")[0]
            svc.remove_op(self.state["server_dir"], name)
            self.refresh_lists()

    def add_wl(self):
        name = self.wl_name.text().strip()
        uuid = self.wl_uuid.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing", "Enter a player name.")
            return
        if uuid and not svc.validate_uuid(uuid):
            QtWidgets.QMessageBox.warning(self, "Invalid UUID", "Enter a valid UUID or leave empty.")
            return
        svc.add_whitelist(self.state["server_dir"], name, uuid or None)
        self.refresh_lists()

    def remove_wl(self):
        item = self.wl_list.currentItem()
        if item:
            name = item.text().split(" (")[0]
            svc.remove_whitelist(self.state["server_dir"], name)
            self.refresh_lists()

class PluginsTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.list = QtWidgets.QListWidget()
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.upload_btn = QtWidgets.QPushButton("Upload plugin jar")
        self.remove_btn = QtWidgets.QPushButton("Remove selected")
        self.disable_btn = QtWidgets.QPushButton("Disable selected")
        self.enable_btn = QtWidgets.QPushButton("Enable selected")

        self.upload_btn.clicked.connect(self.upload_plugin)
        self.remove_btn.clicked.connect(self.remove_plugin)
        self.disable_btn.clicked.connect(self.disable_plugin)
        self.enable_btn.clicked.connect(self.enable_plugin)
        self.refresh_btn.clicked.connect(self.refresh)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.list)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.refresh_btn)
        hl.addWidget(self.upload_btn)
        hl.addWidget(self.remove_btn)
        hl.addWidget(self.disable_btn)
        hl.addWidget(self.enable_btn)
        layout.addLayout(hl)
        layout.addWidget(info_button("Plugins require Paper/Spigot/Purpur server jars. Vanilla ignores plugins.", self))

        self.refresh()

    def refresh(self):
        self.list.clear()
        for p in svc.list_plugins(self.state["server_dir"]):
            self.list.addItem(p.name)

    def upload_plugin(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select plugin jar", "", "Jar Files (*.jar)")
        if f:
            svc.add_plugin(self.state["server_dir"], Path(f))
            self.refresh()

    def remove_plugin(self):
        item = self.list.currentItem()
        if item:
            svc.remove_plugin(self.state["server_dir"], item.text())
            self.refresh()

    def disable_plugin(self):
        item = self.list.currentItem()
        if item:
            svc.disable_plugin(self.state["server_dir"], item.text())
            self.refresh()

    def enable_plugin(self):
        disabled_dir = self.state["server_dir"] / "plugins-disabled"
        disabled = [p.name for p in disabled_dir.glob("*.jar")] if disabled_dir.exists() else []
        if not disabled:
            QtWidgets.QMessageBox.information(self, "None", "No disabled plugins.")
            return
        item, ok = QtWidgets.QInputDialog.getItem(self, "Enable plugin", "Select:", disabled, 0, False)
        if ok and item:
            svc.enable_plugin(self.state["server_dir"], item)
            self.refresh()

class HostToolsTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        backup_box = QtWidgets.QGroupBox("Backups")
        b_layout = QtWidgets.QVBoxLayout()
        self.backup_list = QtWidgets.QListWidget()
        self.make_backup_btn = QtWidgets.QPushButton("Make world backup")
        self.restore_backup_btn = QtWidgets.QPushButton("Restore selected backup")
        self.make_backup_btn.clicked.connect(self.make_backup)
        self.restore_backup_btn.clicked.connect(self.restore_backup)
        b_layout.addWidget(self.backup_list)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.make_backup_btn)
        hl.addWidget(self.restore_backup_btn)
        b_layout.addLayout(hl)
        b_layout.addWidget(info_button("Backups zip the 'world' folder; stop server before restoring to avoid corruption.", self))
        backup_box.setLayout(b_layout)

        sched_box = QtWidgets.QGroupBox("Scheduler")
        s_layout = QtWidgets.QFormLayout()
        self.enable_restart = QtWidgets.QCheckBox("Daily restart")
        self.restart_hour = QtWidgets.QSpinBox(); self.restart_hour.setRange(0, 23)
        self.enable_backup = QtWidgets.QCheckBox("Daily backup")
        self.backup_hour = QtWidgets.QSpinBox(); self.backup_hour.setRange(0, 23)
        self.next_runs_label = QtWidgets.QLabel("Next: —")
        self.update_next_runs()

        self.enable_restart.stateChanged.connect(self.update_next_runs)
        self.enable_backup.stateChanged.connect(self.update_next_runs)
        self.restart_hour.valueChanged.connect(self.update_next_runs)
        self.backup_hour.valueChanged.connect(self.update_next_runs)

        s_layout.addRow(self.row_label("Daily restart at hour:"), self.row_with(self.enable_restart, self.restart_hour, info_button("Automatically sends 'stop' and restarts the server.", self)))
        s_layout.addRow(self.row_label("Daily backup at hour:"), self.row_with(self.enable_backup, self.backup_hour, info_button("Creates a world backup zip once per day.", self)))
        s_layout.addRow("Next scheduled runs:", self.next_runs_label)
        sched_box.setLayout(s_layout)

        fw_box = QtWidgets.QGroupBox("Firewall")
        f_layout = QtWidgets.QHBoxLayout()
        self.open_fw_btn = QtWidgets.QPushButton("Open port 25565")
        self.close_fw_btn = QtWidgets.QPushButton("Remove firewall rule")
        self.open_fw_btn.clicked.connect(self.open_fw)
        self.close_fw_btn.clicked.connect(self.close_fw)
        f_layout.addWidget(self.open_fw_btn)
        f_layout.addWidget(self.close_fw_btn)
        f_layout.addWidget(info_button("Requires elevation. Opens inbound TCP 25565 for external connections. If it fails, try running this application as an Administrator.", self))
        fw_box.setLayout(f_layout)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(backup_box)
        layout.addWidget(sched_box)
        layout.addWidget(fw_box)
        self.refresh_backups()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check_schedule)
        self.timer.start(60 * 1000)

    def open_fw(self):
        try:
            svc.open_firewall_port(25565, "Minecraft")
            QtWidgets.QMessageBox.information(self, "Firewall", "Firewall rule for port 25565 added.\nThis may have required administrator privileges.")
            svc.log(self.state["server_dir"], "Firewall rule for port 25565 added.")
        except Exception as e:
            msg = f"Failed to add firewall rule. Please try running this application as an Administrator.\n\nDetails: {e}"
            QtWidgets.QMessageBox.critical(self, "Firewall Error", msg)

    def close_fw(self):
        try:
            svc.delete_firewall_rule("Minecraft")
            QtWidgets.QMessageBox.information(self, "Firewall", "Firewall rule 'Minecraft' removed.")
            svc.log(self.state["server_dir"], "Firewall rule 'Minecraft' removed.")
        except Exception as e:
            msg = f"Failed to remove firewall rule. Please try running this application as an Administrator.\n\nDetails: {e}"
            QtWidgets.QMessageBox.critical(self, "Firewall Error", msg)

    def row_with(self, *widgets):
        h = QtWidgets.QHBoxLayout()
        w = QtWidgets.QWidget()
        for wd in widgets:
            h.addWidget(wd)
        h.addStretch()
        w.setLayout(h)
        return w

    def row_label(self, text):
        lbl = QtWidgets.QLabel(text)
        return lbl

    def refresh_backups(self):
        self.backup_list.clear()
        for p in svc.list_backups(self.state["server_dir"]):
            self.backup_list.addItem(p.name)

    def make_backup(self):
        try:
            z = svc.make_world_backup(self.state["server_dir"])
            QtWidgets.QMessageBox.information(self, "Backup", f"Created: {z.name}")
            self.refresh_backups()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Backup failed", str(e))
            svc.log(self.state["server_dir"], f"Backup failed: {e}")

    def restore_backup(self):
        item = self.backup_list.currentItem()
        if not item:
            return
        confirm = QtWidgets.QMessageBox.question(self, "Confirm restore", "Stop the server before restoring. Continue?")
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            svc.restore_backup(self.state["server_dir"], self.state["server_dir"] / "backups" / item.text())
            QtWidgets.QMessageBox.information(self, "Restored", "Backup restored.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Restore failed", str(e))
            svc.log(self.state["server_dir"], f"Restore failed: {e}")

    def update_next_runs(self):
        from datetime import timedelta
        now = datetime.now()
        nexts = []

        def get_next_run(hr: int) -> datetime:
            nxt = now.replace(hour=hr, minute=0, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)  # Fixed: properly add 1 day
            return nxt

        if self.enable_restart.isChecked():
            hr = self.restart_hour.value()
            next_time = get_next_run(hr)
            nexts.append(f"restart at {next_time.strftime('%Y-%m-%d %H:%M')}")
        if self.enable_backup.isChecked():
            hr = self.backup_hour.value()
            next_time = get_next_run(hr)
            nexts.append(f"backup at {next_time.strftime('%Y-%m-%d %H:%M')}")
        self.next_runs_label.setText(", ".join(nexts) if nexts else "—")

    def check_schedule(self):
        now = datetime.now()
        if self.enable_backup.isChecked() and now.minute == 0 and now.hour == self.backup_hour.value():
            try:
                svc.make_world_backup(self.state["server_dir"])
            except Exception as e:
                svc.log(self.state["server_dir"], f"Scheduled backup failed: {e}")
        if self.enable_restart.isChecked() and now.minute == 0 and now.hour == self.restart_hour.value():
            svc.log(self.state["server_dir"], "Scheduled restart time reached (send 'stop' in Console).")

class ConsoleTab(QtWidgets.QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.console = QtWidgets.QPlainTextEdit()
        self.console.setReadOnly(True)
        self.cmd_input = QtWidgets.QLineEdit()
        self.cmd_input.setPlaceholderText("Type a server command and press Enter")
        self.cmd_input.returnPressed.connect(self.send_cmd)
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.external_btn = QtWidgets.QPushButton("Open in external CMD")
        self.timestamps_cb = QtWidgets.QCheckBox("Show timestamps")
        self.timestamps_cb.setChecked(self.state.get("console_timestamps", False))
        self.timestamps_cb.stateChanged.connect(self.toggle_timestamps)

        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn.clicked.connect(self.stop_server)
        self.external_btn.clicked.connect(self.open_external)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.console)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(self.cmd_input)
        hl.addWidget(self.start_btn)
        hl.addWidget(self.stop_btn)
        hl.addWidget(self.external_btn)
        hl.addWidget(self.timestamps_cb)
        layout.addLayout(hl)
        layout.addWidget(info_button("Use 'stop' to gracefully shutdown. Timestamps are client-side.", self))

        self.proc = None

    def on_output(self, line: str):
        self.console.appendPlainText(line)

    def on_state(self, s: str):
        self.console.appendPlainText(f"[state] {s}")

    def start_server(self):
        if not self.proc:
            QtWidgets.QMessageBox.warning(self, "Error", "Server process not initialized. Check App Settings.")
            return
        
        # Check if server.jar exists
        jar_path = self.state["server_dir"] / svc.SERVER_JAR_NAME
        if not jar_path.exists():
            QtWidgets.QMessageBox.warning(
                self, "Error", 
                f"server.jar not found at:\n{jar_path}\n\nGo to Setup tab to download or upload a server jar."
            )
            return

        try:
            self.console.clear()
            self.console.appendPlainText("[MCSHoster] Starting server...")
            self.proc.start()
        except FileNotFoundError as e:
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"Java not found. Please install Java and ensure it's in your PATH.\n\nError: {e}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"Failed to start: {e}")

    def stop_server(self):
        if not self.proc:
            QtWidgets.QMessageBox.warning(self, "Error", "No server process to stop.")
            return
        try:
            self.proc.stop()
            self.console.appendPlainText("[MCSHoster] Stop command sent to server...")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to stop server: {e}")

    def send_cmd(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        if not self.proc:
            QtWidgets.QMessageBox.warning(self, "Error", "Server not initialized.")
            return
        try:
            self.proc.send_command(cmd)
            self.console.appendPlainText(f"> {cmd}")
            self.cmd_input.clear()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to send command: {e}")

    def open_external(self):
        try:
            jar = self.state["server_dir"] / svc.SERVER_JAR_NAME
            if not jar.exists():
                QtWidgets.QMessageBox.warning(self, "Error", "server.jar not found. Go to Setup tab first.")
                return
            args = self.state.get("java_args") or ["-Xms1G", "-Xmx1G"]
            cmd_line = " ".join(["java"] + args + ["-jar", f'"{jar}"', "nogui"])
            external_process = QtCore.QProcess(self)
            external_process.setWorkingDirectory(str(self.state["server_dir"]))
            external_process.start("cmd.exe", ["/k", cmd_line])
            self.console.appendPlainText("[MCSHoster] Opened server in external CMD window.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"Failed to open external console: {e}")

    def toggle_timestamps(self, state):
        self.state["console_timestamps"] = state == QtCore.Qt.Checked
        self.proc.timestamps = self.state["console_timestamps"]

class AppSettingsTab(QtWidgets.QWidget):
    def __init__(self, state, apply_settings_callback):
        super().__init__()
        self.state = state
        self.apply_settings = apply_settings_callback

        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.8, 2.0); self.scale_spin.setSingleStep(0.1); self.scale_spin.setValue(self.state["ui_scale"])
        self.xms_spin = QtWidgets.QSpinBox(); self.xms_spin.setRange(256, 16384); self.xms_spin.setSuffix(" MB")
        self.xmx_spin = QtWidgets.QSpinBox(); self.xmx_spin.setRange(512, 32768); self.xmx_spin.setSuffix(" MB")
        ja = self.state.get("java_args") or ["-Xms1G", "-Xmx1G"]

        def parse_mem_arg(arg_str, default_mb):
            match = re.match(r"-Xm[sx](\d+)([GgMm])", arg_str)
            if not match: return default_mb
            val, unit = int(match.group(1)), match.group(2).upper()
            return val * 1024 if unit == 'G' else val

        try:
            self.xms_spin.setValue(parse_mem_arg(ja[0], 1024))
            self.xmx_spin.setValue(parse_mem_arg(ja[1], 2048))
        except:
            self.xms_spin.setValue(1024); self.xmx_spin.setValue(2048) # Fallback

        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.apply_btn.clicked.connect(self.on_apply)

        form = QtWidgets.QFormLayout(self)
        form.addRow("UI scale:", self.row_with(self.scale_spin, info_button("Multiply UI size to your preference.", self)))
        form.addRow("Java Xms (min):", self.row_with(self.xms_spin, info_button("Initial Java heap (RAM) for server).", self)))
        form.addRow("Java Xmx (max):", self.row_with(self.xmx_spin, info_button("Maximum Java heap (RAM) for server).", self)))
        form.addRow(self.apply_btn)

    def row_with(self, *widgets):
        h = QtWidgets.QHBoxLayout()
        w = QtWidgets.QWidget()
        for wd in widgets:
            h.addWidget(wd)
        h.addStretch()
        w.setLayout(h)
        return w

    def on_apply(self):
        xms = self.xms_spin.value()
        xmx = self.xmx_spin.value()
        
        # Validate memory settings
        if xms > xmx:
            QtWidgets.QMessageBox.warning(
                self, "Invalid Settings", 
                "Minimum RAM cannot be greater than Maximum RAM.\n\nPlease adjust the values."
            )
            return
        
        if xmx < 512:
            QtWidgets.QMessageBox.warning(
                self, "Invalid Settings",
                "Maximum RAM should be at least 512 MB for a Minecraft server."
            )
            return
        
        self.state["ui_scale"] = self.scale_spin.value()
        self.state["java_args"] = [f"-Xms{xms}M", f"-Xmx{xmx}M"]
        self.apply_settings()
        QtWidgets.QMessageBox.information(self, APP_NAME, "Settings applied successfully!\n\nNote: Memory changes will apply on next server start.")

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        self.config_path = Path(__file__).parent / "config.json"
        default_state = {
            "server_dir": svc.DEFAULT_SERVER_DIR,
            "java_args": ["-Xms1G", "-Xmx1G"],
            "console_timestamps": False,
            "ui_scale": 1.0
        }
        self.state = svc.read_json(self.config_path, default_state)
        # Ensure server_dir is a Path object for consistency
        self.state["server_dir"] = Path(self.state["server_dir"])
        
        tabs = QtWidgets.QTabWidget()
        self.setup_tab = SetupTab(self.state)
        self.settings_tab = SettingsTab(self.state)
        self.users_tab = UsersTab(self.state)
        self.plugins_tab = PluginsTab(self.state)
        self.host_tools_tab = HostToolsTab(self.state)
        self.console_tab = ConsoleTab(self.state)
        self.app_settings_tab = AppSettingsTab(self.state, self.apply_app_settings)

        tabs.addTab(self.setup_tab, "Setup")
        tabs.addTab(self.settings_tab, "Settings")
        tabs.addTab(self.users_tab, "Users")
        tabs.addTab(self.plugins_tab, "Plugins")
        tabs.addTab(self.host_tools_tab, "Host tools")
        tabs.addTab(self.console_tab, "Console")
        tabs.addTab(self.app_settings_tab, "App settings")

        tabs.currentChanged.connect(self.on_tab_changed)

        self.setCentralWidget(tabs)
        self.apply_app_settings()

    def reinitialize_tabs(self):
        self.console_tab.proc = svc.ServerProcess(
            self.state["server_dir"], self.state.get("java_args"), self.state.get("console_timestamps", False)
        )
        self.console_tab.proc.on_output = self.console_tab.on_output
        self.console_tab.proc.on_state = self.console_tab.on_state

    def on_tab_changed(self, index):
        widget = self.centralWidget().widget(index)
        if widget == self.settings_tab:
            self.settings_tab.load_props()
        elif widget == self.users_tab:
            self.users_tab.refresh_lists()
        elif widget == self.host_tools_tab:
            self.host_tools_tab.refresh_backups()

    def apply_app_settings(self):
        scale = self.state.get("ui_scale", 1.0)
        font = QtGui.QFont()
        # Use the application-wide font for scaling
        app_font = QtWidgets.QApplication.instance().font()
        app_font.setPointSizeF(10 * scale)
        QtWidgets.QApplication.instance().setFont(app_font)
        self.reinitialize_tabs()

    def closeEvent(self, event):
        # Convert Path back to string for JSON serialization
        self.state["server_dir"] = str(self.state["server_dir"])
        svc.write_json(self.config_path, self.state)
        super().closeEvent(event)

def main():
    app = QtWidgets.QApplication(sys.argv)
    qss_path = Path(__file__).parent / "styles.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()