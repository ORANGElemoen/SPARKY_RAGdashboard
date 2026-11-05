"""The backup zip must hold a usable database copy plus the files git doesn't keep."""
import importlib.util
import sqlite3
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup_sparky.py"
spec = importlib.util.spec_from_file_location("backup_sparky", SCRIPT)
backup_sparky = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_sparky)

TABLES = ("documents", "chunks", "embeddings", "devices", "interaction_log")


def make_project(root: Path) -> None:
    (root / "data/storage/uploads").mkdir(parents=True)
    (root / "data/storage/uploads/sheet.pdf").write_bytes(b"%PDF")
    (root / "data/studio/voice").mkdir(parents=True)
    (root / "data/studio/voice/line.wav").write_bytes(b"RIFF")
    (root / "data/studio/studio.json").write_text("{}")
    (root / "data/piper_voices").mkdir()
    (root / "data/piper_voices/en_US-sparky-medium.onnx").write_bytes(b"voice")
    (root / "data/piper_voices/en_US-sparky-medium.onnx.json").write_text("{}")
    (root / "data/piper_voices/en_US-hfc_female-medium.onnx").write_bytes(b"stock")
    db = sqlite3.connect(root / "data/rag_database.db")
    for table in TABLES:
        db.execute(f"CREATE TABLE {table} (id INTEGER)")
    db.execute("INSERT INTO documents VALUES (1)")
    db.commit()
    db.close()


def test_backup_contains_private_data_and_a_working_database(tmp_path):
    root = tmp_path / "project"
    make_project(root)

    path, counts, missing = backup_sparky.create_backup(root, tmp_path / "out")

    assert counts["documents"] == 1
    assert missing == []
    assert not list((tmp_path / "out").glob("*.partial"))
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        z.extract("data/rag_database.db", tmp_path / "restored")
    assert {"data/rag_database.db", "data/storage/uploads/sheet.pdf", "data/studio/studio.json",
            "data/studio/voice/line.wav", "data/piper_voices/en_US-sparky-medium.onnx",
            "BACKUP_INFO.txt"} <= names
    assert "data/piper_voices/en_US-hfc_female-medium.onnx" not in names  # can be downloaded again
    db = sqlite3.connect(tmp_path / "restored/data/rag_database.db")
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    db.close()


def test_missing_voice_is_reported_not_fatal(tmp_path):
    root = tmp_path / "project"
    make_project(root)
    (root / "data/piper_voices/en_US-sparky-medium.onnx").unlink()

    _, _, missing = backup_sparky.create_backup(root, tmp_path / "out")

    assert missing == ["data/piper_voices/en_US-sparky-medium.onnx"]


def test_missing_database_fails_without_leaving_a_zip(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_sparky.create_backup(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()
