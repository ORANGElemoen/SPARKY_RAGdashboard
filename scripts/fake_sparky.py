#!/usr/bin/env python3
"""
A pretend Sparky for testing the Wi-Fi personality pack without hardware.

Does exactly what the ESP32 firmware does (firmware/sparky/src/pack_sync.cpp
copies plan_sync): fetch the pack with If-None-Match, download only missing
voice lines into a folder, switch the manifest over last, report back with
an ack, and long-poll for "Send to Sparky now" faces (printed as LED art).

Usage:
    python scripts/fake_sparky.py --key <device API key from the Devices page>
    python scripts/fake_sparky.py --key ... --once      # one sync, then exit
"""
import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Dict, List, Tuple

import httpx


def plan_sync(manifest: dict, have: Dict[str, int]) -> Tuple[List[dict], List[str]]:
    """Voice lines to download (missing or wrong size) and ids to delete (no longer in the pack)."""
    wanted = {v["id"]: v for v in manifest.get("voice_lines", [])}
    download = [v for i, v in wanted.items() if have.get(i) != v["bytes"]]
    delete = sorted(i for i in have if i not in wanted)
    return download, delete


def face_art(rows: List[str]) -> str:
    return "\n".join(" ".join("@" if ch == "#" else "." for ch in row) for row in rows)


class FakeSparky:
    def __init__(self, base_url: str, key: str, folder: Path):
        self.http = httpx.Client(base_url=base_url, headers={"X-Device-Key": key}, timeout=35)
        self.folder = folder
        self.voice = folder / "voice"
        self.voice.mkdir(parents=True, exist_ok=True)

    def version(self) -> str:
        f = self.folder / "version.txt"
        return f.read_text().strip() if f.exists() else ""

    def sync(self) -> None:
        headers = {"If-None-Match": f'"{self.version()}"'} if self.version() else {}
        r = self.http.get("/api/v1/device/pack", headers=headers)
        if r.status_code == 304:
            print("pack up to date:", self.version())
            return
        r.raise_for_status()
        manifest = r.json()
        have = {p.stem: p.stat().st_size for p in self.voice.glob("*.wav")}
        download, delete = plan_sync(manifest, have)
        for line in download:                              # 1. download new files (old pack still valid)
            tmp = self.voice / f"{line['id']}.tmp"
            with self.http.stream("GET", f"/api/v1/device/pack/voice/{line['id']}.wav") as resp:
                resp.raise_for_status()
                with tmp.open("wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
            if tmp.stat().st_size != line["bytes"]:
                tmp.unlink()
                raise RuntimeError(f"voice line {line['id']} arrived incomplete")
            shutil.move(tmp, self.voice / f"{line['id']}.wav")
        tmp_manifest = self.folder / "manifest.tmp"          # 2. switch over: manifest, then version
        tmp_manifest.write_text(json.dumps(manifest))
        shutil.move(tmp_manifest, self.folder / "manifest.json")
        (self.folder / "version.txt").write_text(manifest["pack_version"])
        for line_id in delete:                             # 3. tidy up leftovers
            (self.voice / f"{line_id}.wav").unlink(missing_ok=True)
        used = sum(p.stat().st_size for p in self.voice.glob("*.wav"))
        self.http.post("/api/v1/device/pack/ack", json={"pack_version": manifest["pack_version"],
                                                        "free_bytes": max(0, 1_300_000 - used)}).raise_for_status()
        print(f"updated to pack {manifest['pack_version']}: {len(manifest['faces'])} faces, "
              f"{len(download)} downloaded, {len(delete)} deleted")

    def listen(self) -> None:
        r = self.http.get("/api/v1/device/commands", params={"wait": 25})
        r.raise_for_status()
        if r.status_code == 204:
            return
        command = r.json()
        if command.get("type") == "sync":
            self.sync()
        elif command.get("type") == "show_face":
            print(f"\nShowing face for {command.get('seconds', 10)} s:\n{face_art(command['rows'])}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--key", required=True, help="device API key from the Devices page")
    ap.add_argument("--folder", default="data/fake_sparky")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    sparky = FakeSparky(args.base_url, args.key, Path(args.folder))
    sparky.sync()
    if args.once:
        return
    last = time.time()
    while True:
        try:
            sparky.listen()
            if time.time() - last > 300:   # same 5-minute check as the real Sparky
                sparky.sync()
                last = time.time()
        except httpx.HTTPError as e:       # server down or key revoked - keep going like the real one
            print("server problem, retrying in 5 s:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
