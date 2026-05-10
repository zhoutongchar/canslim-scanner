from __future__ import annotations

from pathlib import Path

from canslim.universe.base import Universe


class CustomUniverse(Universe):
    name = "custom"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[str]:
        if not self.path.exists():
            raise FileNotFoundError(f"Universe file not found: {self.path}")
        out: list[str] = []
        for line in self.path.read_text().splitlines():
            t = line.strip().upper()
            if not t or t.startswith("#"):
                continue
            out.append(t.split(",")[0].strip())  # tolerate CSV-with-extra-cols
        return sorted(set(out))
