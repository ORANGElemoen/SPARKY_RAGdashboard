#!/usr/bin/env python3
"""
Backs up everything Sparky needs that git does not hold, into one zip:

    data/rag_database.db   documents, chunks, embeddings, device keys, question log
    data/storage/          the uploaded PDFs
    data/studio/           voice lines and faces
    data/piper_voices/     Sparky's trained voice (the stock voices can be downloaded again)
    .env                   local settings, if there is one

Safe to run while the server is on: the database is copied with SQLite's backup API.

The zip holds private data, so keep it out of git (this repository is public). Copy it
somewhere off this laptop. To restore, see docs/NEW_MACHINE.md.

    python scripts/backup_sparky.py                     # writes to backups/
    python scripts/backup_sparky.py --to D:/somewhere
"""
import argparse
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATABASE = Path("data/rag_database.db")
FOLDERS = [Path("data/storage"), Path("data/studio")]
SPARKY_VOICE_FILES = [Path("data/piper_voices/en_US-sparky-medium.onnx"),
                      Path("data/piper_voices/en_US-sparky-medium.onnx.json")]
OPTIONAL_FILES = [Path(".env")]


def snapshot_database(source: Path, target: Path) -> dict:
    """Copy a possibly in-use SQLite database, check the copy, and return its row counts."""
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        with dst:
            src.backup(dst)
        status = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if status != "ok":
            raise RuntimeError(f"Database copy failed its integrity check: {status}")
        return {table: dst.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("documents", "chunks", "embeddings", "devices", "interaction_log")}
    finally:
        src.close()
        dst.close()


def git_commit(root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True,
                              capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def create_backup(root: Path, out_dir: Path) -> tuple:
    """Write the zip, returning (zip path, row counts, missing items). Raises if the database is missing."""
    if not (root / DATABASE).exists():
        raise FileNotFoundError(f"No database at {root / DATABASE}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final = out_dir / f"sparky_backup_{stamp}.zip"
    partial = final.with_suffix(".zip.partial")
    missing = []
    try:
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            db_copy = Path(tmp) / "snapshot.db"
            counts = snapshot_database(root / DATABASE, db_copy)
            z.write(db_copy, DATABASE.as_posix())

            for folder in FOLDERS:
                if not (root / folder).is_dir():
                    missing.append(folder.as_posix())
                    continue
                for path in sorted((root / folder).rglob("*")):
                    if path.is_file():
                        z.write(path, path.relative_to(root).as_posix())

            for rel in SPARKY_VOICE_FILES:
                if (root / rel).exists():
                    z.write(root / rel, rel.as_posix())
                else:
                    missing.append(rel.as_posix())
            for rel in OPTIONAL_FILES:
                if (root / rel).exists():
                    z.write(root / rel, rel.as_posix())

            lines = [f"created: {stamp}", f"git commit: {git_commit(root)}"]
            lines += [f"{table}: {count}" for table, count in counts.items()]
            lines += [f"missing: {item}" for item in missing]
            z.writestr("BACKUP_INFO.txt", "\n".join(lines) + "\n")

        with zipfile.ZipFile(partial) as z:
            bad = z.testzip()
            if bad:
                raise RuntimeError(f"Backup zip is damaged at {bad}")
        partial.replace(final)
    finally:
        partial.unlink(missing_ok=True)
    return final, counts, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up Sparky's private data into one zip.")
    parser.add_argument("--to", type=Path, default=ROOT / "backups", help="folder for the zip (default: backups/)")
    args = parser.parse_args()
    try:
        path, counts, missing = create_backup(ROOT, args.to)
    except (OSError, RuntimeError, sqlite3.Error) as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        return 1
    print(f"Backup written: {path} ({path.stat().st_size / 1_000_000:.1f} MB)")
    print("Contains: " + ", ".join(f"{count} {table}" for table, count in counts.items()))
    for item in missing:
        print(f"Not found, so not included: {item}")
    print("Now copy it somewhere off this laptop. It holds private data: keep it out of git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
