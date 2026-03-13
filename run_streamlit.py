from __future__ import annotations

import sys
from pathlib import Path


def _add_src_to_path() -> None:
    src_path = Path(__file__).resolve().parent / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


_add_src_to_path()

from luxnews.desktop_launcher import main


if __name__ == "__main__":
    main()
