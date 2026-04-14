import hashlib
import json
import platform
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class SessionStore:
    def __init__(self, file_path: str = "session.json") -> None:
        self.path = Path(file_path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def build_device_profile() -> Dict[str, str]:
    hostname = socket.gethostname()
    mac_address = f"{uuid.getnode():012x}"
    mac_hash = hashlib.sha256(mac_address.encode("utf-8")).hexdigest()
    install_seed = f"{hostname}:{platform.platform()}:{mac_hash}"
    install_id = hashlib.sha256(install_seed.encode("utf-8")).hexdigest()[:24]
    return {
        "deviceFingerprint": hashlib.sha256(
            f"{hostname}:{mac_hash}".encode("utf-8")
        ).hexdigest()[:32],
        "installId": install_id,
        "primaryMacHash": mac_hash,
        "macListHash": mac_hash,
        "deviceName": hostname,
        "deviceType": "PC",
        "clientType": "DESKTOP",
        "osType": platform.system() or "Unknown",
        "osVersion": platform.version(),
        "loginIp": "127.0.0.1",
    }


def new_request_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
