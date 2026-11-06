#!/usr/bin/env python3
"""
Copies Sparky's current content into .docker-seed/ (gitignored), ready to build into the image:
the database, sheets, voice lines, faces and Sparky's voice.

Safe while the server is running. The database copy has its file paths changed to the container's,
because the real database stores Windows paths and PDF downloads would fail otherwise.
"""
import shutil
import sqlite3
import sys
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / ".docker-seed" / "data"
UPLOADS_IN_CONTAINER = "/app/data/storage/uploads"


def copy_database(source: Path, target: Path) -> int:
    """Snapshot the database, then point its documents at the container's upload folder."""
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        with dst:
            src.backup(dst)
        rows = dst.execute("SELECT id, file_path FROM documents WHERE file_path != ''").fetchall()
        with dst:
            for doc_id, path in rows:
                name = PureWindowsPath(path).name
                dst.execute("UPDATE documents SET file_path = ? WHERE id = ?", (f"{UPLOADS_IN_CONTAINER}/{name}", doc_id))
        dst.execute("PRAGMA journal_mode=DELETE")
        return len(rows)
    finally:
        src.close()
        dst.close()


def prepare(root: Path, seed: Path) -> int:
    data = root / "data"
    if not (data / "rag_database.db").exists():
        raise FileNotFoundError(f"No database at {data / 'rag_database.db'}")
    if seed.exists():
        shutil.rmtree(seed)
    seed.mkdir(parents=True)
    for folder in ("storage", "studio"):
        if (data / folder).is_dir():
            shutil.copytree(data / folder, seed / folder)
    voices = seed / "piper_voices"
    voices.mkdir()
    for name in ("en_US-sparky-medium.onnx", "en_US-sparky-medium.onnx.json"):
        if not (data / "piper_voices" / name).exists():
            raise FileNotFoundError(f"Sparky's voice is missing: {name}")
        shutil.copy2(data / "piper_voices" / name, voices / name)
    return copy_database(data / "rag_database.db", seed / "rag_database.db")


if __name__ == "__main__":
    try:
        count = prepare(ROOT, SEED)
    except (OSError, sqlite3.Error) as e:
        print(f"Couldn't prepare the content: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Prepared {SEED} with {count} documents")
