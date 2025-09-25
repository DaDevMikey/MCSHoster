import json
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Defaults and constants
APP_NAME = "MCSHoster"
DEFAULT_SERVER_DIR = Path.home() / "Documents" / "MinecraftServer"
SERVER_JAR_NAME = "server.jar"
LOG_FILE_NAME = "mcs_hoster.log"

MOJANG_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

SERVER_TYPES = ["Vanilla", "Paper", "Spigot", "Purpur", "Custom"]

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def log_path(server_dir: Path) -> Path:
    ensure_dir(server_dir)
    return server_dir / LOG_FILE_NAME

def log(server_dir: Path, msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with log_path(server_dir).open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass  # final fallback, avoid cascading errors

def download_bytes(url: str, timeout: int = 45) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

def get_versions() -> List[Dict]:
    """Return list of Mojang versions (id, type, url)."""
    r = requests.get(MOJANG_MANIFEST_URL, timeout=45)
    r.raise_for_status()
    manifest = r.json()
    return manifest.get("versions", [])

def resolve_version_meta(version_id: str) -> Dict:
    for v in get_versions():
        if v["id"] == version_id:
            r = requests.get(v["url"], timeout=45)
            r.raise_for_status()
            return r.json()
    raise ValueError(f"Version {version_id} not found in Mojang manifest")

def get_server_download_url(version_id: str) -> str:
    meta = resolve_version_meta(version_id)
    server = meta.get("downloads", {}).get("server", {})
    url = server.get("url")
    if not url:
        raise ValueError("Server URL not found for this version")
    return url

def write_text(path: Path, text: str):
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def read_properties(path: Path) -> Dict[str, str]:
    props = {}
    if not path.exists():
        return props
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
    return props

def write_properties(path: Path, props: Dict[str, str]):
    backup = path.with_suffix(".bak")
    if path.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")

def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(read_text(path))

def write_json(path: Path, data):
    backup = path.with_suffix(".bak")
    if path.exists():
        shutil.copy2(path, backup)
    write_text(path, json.dumps(data, indent=2))

def set_eula(server_dir: Path, accept: bool):
    write_text(server_dir / "eula.txt", f"eula={'true' if accept else 'false'}\n")

def download_server_jar(server_dir: Path, version_id: str):
    url = get_server_download_url(version_id)
    ensure_dir(server_dir)
    jar_path = server_dir / SERVER_JAR_NAME
    jar_path.write_bytes(download_bytes(url))
    log(server_dir, f"Downloaded Vanilla server.jar for version {version_id}")

def place_custom_server_jar(server_dir: Path, source_path: Path):
    target = server_dir / SERVER_JAR_NAME
    ensure_dir(server_dir)
    shutil.copy2(source_path, target)
    log(server_dir, f"Placed custom server.jar from {source_path}")

def bootstrap_server(server_dir: Path, java_args: Optional[List[str]] = None) -> Tuple[bool, str]:
    jar = server_dir / SERVER_JAR_NAME
    if not jar.exists():
        return False, "server.jar not found"
    cmd = ["java", "-jar", str(jar), "nogui"]
    if java_args:
        cmd = ["java"] + java_args + ["-jar", str(jar), "nogui"]
    try:
        proc = subprocess.Popen(cmd, cwd=str(server_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        log(server_dir, f"Bootstrap failed to start: {e}")
        return False, f"Failed to start java: {e}"
    output_lines = []
    start_time = time.time()
    generated = False
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            output_lines.append(line)
            if "You need to agree to the EULA" in line or "Failed to load eula.txt" in line:
                generated = True
                proc.terminate()
                break
            if (server_dir / "eula.txt").exists() and (server_dir / "server.properties").exists():
                generated = True
                proc.terminate()
                break
        if time.time() - start_time > 45:
            proc.terminate()
            break
    log(server_dir, "Bootstrap completed" if generated else "Bootstrap did not generate expected files")
    return generated, "".join(output_lines)

class ServerProcess:
    def __init__(self, server_dir: Path, java_args: Optional[List[str]] = None, timestamps: bool = False):
        self.server_dir = server_dir
        self.java_args = java_args or ["-Xms1G", "-Xmx1G"]
        self.proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self.on_output = None  # callable(str)
        self.on_state = None   # callable(str)
        self.timestamps = timestamps

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        jar = self.server_dir / SERVER_JAR_NAME
        if not jar.exists():
            raise FileNotFoundError("server.jar not found")
        cmd = ["java"] + self.java_args + ["-jar", str(jar), "nogui"]
        try:
            self.proc = subprocess.Popen(cmd, cwd=str(self.server_dir),
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.PIPE, text=True, bufsize=1,
                                         encoding='utf-8', errors='replace')
            if self.on_state: self.on_state("running")
            self._reader_thread = threading.Thread(target=self._reader, daemon=True)
            self._reader_thread.start()
            log(self.server_dir, f"Server started with cmd: {' '.join(cmd)}")
        except Exception as e:
            log(self.server_dir, f"Failed to start server: {e}")
            raise

    def _reader(self):
        try:
            for line in self.proc.stdout:
                msg = line.rstrip()
                if self.timestamps:
                    ts = datetime.now().strftime("%H:%M:%S")
                    msg = f"[{ts}] {msg}"
                if self.on_output: self.on_output(msg)
        except Exception as e:
            log(self.server_dir, f"Reader thread error: {e}")
        finally:
            if self.on_state: self.on_state("stopped")
            log(self.server_dir, "Server process stopped")

    def send_command(self, cmd: str):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
                log(self.server_dir, f"Sent command: {cmd}")
            except Exception as e:
                log(self.server_dir, f"Failed to send command '{cmd}': {e}")

    def stop(self):
        self.send_command("stop")

# Plugin helpers (Bukkit/Spigot/Paper/Purpur style)
def list_plugins(server_dir: Path) -> List[Path]:
    plugins_dir = server_dir / "plugins"
    if not plugins_dir.exists():
        return []
    return sorted([p for p in plugins_dir.glob("*.jar") if p.is_file()])

def ensure_plugins_dir(server_dir: Path) -> Path:
    p = server_dir / "plugins"
    ensure_dir(p)
    return p

def add_plugin(server_dir: Path, jar_source: Path):
    plugins_dir = ensure_plugins_dir(server_dir)
    shutil.copy2(jar_source, plugins_dir / jar_source.name)
    log(server_dir, f"Plugin added: {jar_source.name}")

def remove_plugin(server_dir: Path, plugin_name: str):
    plugins_dir = server_dir / "plugins"
    target = plugins_dir / plugin_name
    if target.exists():
        target.unlink()
        log(server_dir, f"Plugin removed: {plugin_name}")

def disable_plugin(server_dir: Path, plugin_name: str):
    disabled_dir = server_dir / "plugins-disabled"
    ensure_dir(disabled_dir)
    src = server_dir / "plugins" / plugin_name
    if src.exists():
        shutil.move(str(src), str(disabled_dir / plugin_name))
        log(server_dir, f"Plugin disabled: {plugin_name}")

def enable_plugin(server_dir: Path, plugin_name: str):
    plugins_dir = ensure_plugins_dir(server_dir)
    disabled_dir = server_dir / "plugins-disabled"
    src = disabled_dir / plugin_name
    if src.exists():
        shutil.move(str(src), str(plugins_dir / plugin_name))
        log(server_dir, f"Plugin enabled: {plugin_name}")

# Users helpers
def validate_uuid(uuid: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", uuid))

def add_op(server_dir: Path, name: str, uuid: Optional[str] = None, level: int = 4):
    ops_path = server_dir / "ops.json"
    ops = read_json(ops_path, [])
    new_entry = {"name": name, "level": level, "bypassesPlayerLimit": False}
    if uuid: new_entry["uuid"] = uuid
    for e in ops:
        if e.get("name") == name or (uuid and e.get("uuid") == uuid):
            return
    ops.append(new_entry)
    write_json(ops_path, ops)
    log(server_dir, f"OP added: {name}")

def remove_op(server_dir: Path, name: str):
    ops_path = server_dir / "ops.json"
    ops = read_json(ops_path, [])
    ops = [e for e in ops if e.get("name") != name]
    write_json(ops_path, ops)
    log(server_dir, f"OP removed: {name}")

def add_whitelist(server_dir: Path, name: str, uuid: Optional[str] = None):
    wl_path = server_dir / "whitelist.json"
    wl = read_json(wl_path, [])
    new_entry = {"name": name}
    if uuid: new_entry["uuid"] = uuid
    for e in wl:
        if e.get("name") == name:
            return
    wl.append(new_entry)
    write_json(wl_path, wl)
    log(server_dir, f"Whitelisted: {name}")

def remove_whitelist(server_dir: Path, name: str):
    wl_path = server_dir / "whitelist.json"
    wl = read_json(wl_path, [])
    wl = [e for e in wl if e.get("name") != name]
    write_json(wl_path, wl)
    log(server_dir, f"Whitelist removed: {name}")

# Backups
def worlds_dir(server_dir: Path) -> Path:
    # Typically world directory is `world` by default
    return server_dir / "world"

def backup_dir(server_dir: Path) -> Path:
    d = server_dir / "backups"
    ensure_dir(d)
    return d

def make_world_backup(server_dir: Path, world_folder: Optional[Path] = None) -> Path:
    wf = world_folder or worlds_dir(server_dir)
    if not wf.exists():
        raise FileNotFoundError("World folder not found (e.g., 'world')")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir(server_dir) / f"world_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(wf):
            for file in files:
                full = Path(root) / file
                rel = full.relative_to(wf.parent)
                z.write(full, rel)
    log(server_dir, f"World backup created: {zip_path.name}")
    return zip_path

def list_backups(server_dir: Path) -> List[Path]:
    return sorted(backup_dir(server_dir).glob("*.zip"))

def restore_backup(server_dir: Path, backup_zip: Path):
    if not backup_zip.exists():
        raise FileNotFoundError("Backup zip not found")
    # Stop server is recommended before restore
    target_parent = worlds_dir(server_dir).parent
    # Move current world to world_old_TIMESTAMP
    world = worlds_dir(server_dir)
    if world.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(str(world), str(target_parent / f"world_old_{ts}"))
    with zipfile.ZipFile(backup_zip, "r") as z:
        z.extractall(target_parent)
    log(server_dir, f"World restored from: {backup_zip.name}")

# Firewall helpers (requires elevation when executed)
def open_firewall_port(port: int, name: str = "Minecraft"):
    subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={name}",
                    "dir=in", "action=allow", "protocol=TCP", f"localport={port}"], check=True, capture_output=True)

def delete_firewall_rule(name: str):
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"], check=True, capture_output=True)