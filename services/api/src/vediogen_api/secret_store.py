import json
from pathlib import Path

from cryptography.fernet import Fernet


class LocalEncryptedSecretStore:
    """Small local adapter; production deployments replace this with a managed secret store."""

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self._key_path = data_dir / "master.key"
        self._store_path = data_dir / "secrets.enc.json"
        if not self._key_path.exists():
            self._key_path.write_bytes(Fernet.generate_key())
        self._cipher = Fernet(self._key_path.read_bytes())

    def put(self, secret_ref: str, value: str) -> None:
        values = self._read()
        values[secret_ref] = self._cipher.encrypt(value.encode("utf-8")).decode("ascii")
        self._store_path.write_text(json.dumps(values), encoding="utf-8")

    def get(self, secret_ref: str) -> str:
        encrypted = self._read()[secret_ref]
        return self._cipher.decrypt(encrypted.encode("ascii")).decode("utf-8")

    def delete(self, secret_ref: str) -> None:
        values = self._read()
        values.pop(secret_ref, None)
        self._store_path.write_text(json.dumps(values), encoding="utf-8")

    def _read(self) -> dict[str, str]:
        if not self._store_path.exists():
            return {}
        return json.loads(self._store_path.read_text(encoding="utf-8"))
