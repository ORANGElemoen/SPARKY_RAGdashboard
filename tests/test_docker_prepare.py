"""The image's copy of the database must point at the container's files, and leave the real one alone."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "docker_prepare.py"
spec = importlib.util.spec_from_file_location("docker_prepare", SCRIPT)
docker_prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_prepare)

WINDOWS_PATH = r"C:\Users\someone\Sparky\data\storage\uploads\20261105_Lemon Battery.pdf"


def make_project(root):
    (root / "data/storage/uploads").mkdir(parents=True)
    (root / "data/storage/uploads/20261105_Lemon Battery.pdf").write_bytes(b"%PDF")
    (root / "data/studio/voice").mkdir(parents=True)
    (root / "data/studio/studio.json").write_text("{}")
    (root / "data/piper_voices").mkdir()
    for name in ("en_US-sparky-medium.onnx", "en_US-sparky-medium.onnx.json", "en_US-hfc_female-medium.onnx"):
        (root / "data/piper_voices" / name).write_bytes(b"x")
    db = sqlite3.connect(root / "data/rag_database.db")
    db.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, file_path TEXT)")
    db.execute("INSERT INTO documents VALUES (1, ?), (2, '')", (WINDOWS_PATH,))
    db.commit()
    db.close()


def test_the_copy_uses_container_paths_and_the_real_database_is_untouched(tmp_path):
    make_project(tmp_path)
    seed = tmp_path / "seed"

    assert docker_prepare.prepare(tmp_path, seed) == 1

    copy = sqlite3.connect(seed / "rag_database.db")
    assert copy.execute("SELECT file_path FROM documents WHERE id = 1").fetchone()[0] == \
        "/app/data/storage/uploads/20261105_Lemon Battery.pdf"
    assert copy.execute("SELECT file_path FROM documents WHERE id = 2").fetchone()[0] == ""
    copy.close()
    real = sqlite3.connect(tmp_path / "data/rag_database.db")
    assert real.execute("SELECT file_path FROM documents WHERE id = 1").fetchone()[0] == WINDOWS_PATH
    real.close()


def test_only_sparkys_voice_is_copied(tmp_path):
    make_project(tmp_path)
    docker_prepare.prepare(tmp_path, tmp_path / "seed")
    voices = {p.name for p in (tmp_path / "seed/piper_voices").iterdir()}
    assert voices == {"en_US-sparky-medium.onnx", "en_US-sparky-medium.onnx.json"}


def test_a_missing_voice_stops_the_build(tmp_path):
    make_project(tmp_path)
    (tmp_path / "data/piper_voices/en_US-sparky-medium.onnx").unlink()
    with pytest.raises(FileNotFoundError):
        docker_prepare.prepare(tmp_path, tmp_path / "seed")
