"""Storage boundary: business code only sees opaque keys and bytes."""
import re
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class Storage(Protocol):
    def put(self, content: bytes) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.jpg", key):
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid storage path")
        return path

    def put(self, content: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = f"{uuid4().hex}.jpg"
        path = self.path(key)
        with path.open("xb") as output:
            try:
                output.write(content)
            except OSError:
                output.close()
                path.unlink(missing_ok=True)
                raise
        return key

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
