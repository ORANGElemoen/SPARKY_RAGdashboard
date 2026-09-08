#!/usr/bin/env python3
"""
Simulate several ESP32-like hardware devices hammering the tutor's API
concurrently.

No physical hardware exists yet, but this exercises the exact things the
hardware phase depends on - the asyncio.to_thread concurrency fix, the
per-device API key auth, and the voice endpoint's concurrency cap - against
a real running server, so they're proven out before any firmware exists.

Usage: python scripts/simulate_devices.py [--base-url http://127.0.0.1:8001]
"""
import argparse
import asyncio
import io
import time
import wave

import httpx


def make_silence_wav(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * int(sample_rate * seconds))
    return buf.getvalue()


async def get_csrf(client: httpx.AsyncClient) -> str:
    r = await client.get("/api/v1/csrf-token")
    r.raise_for_status()
    return r.json()["csrf_token"]


async def provision_device(client: httpx.AsyncClient, csrf: str, name: str):
    r = await client.post(
        "/admin/devices", json={"name": name}, headers={"X-CSRF-Token": csrf}
    )
    r.raise_for_status()
    data = r.json()
    return data["id"], data["api_key"]


async def revoke_device(client: httpx.AsyncClient, csrf: str, device_id: int):
    r = await client.delete(
        f"/admin/devices/{device_id}", headers={"X-CSRF-Token": csrf}
    )
    r.raise_for_status()


async def timed_query(client: httpx.AsyncClient, device_key: str, query: str, label: str):
    t0 = time.monotonic()
    r = await client.post(
        "/api/v1/query", json={"query": query}, headers={"X-Device-Key": device_key}
    )
    return label, r.status_code, time.monotonic() - t0


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=120) as client:
        print("== Provisioning test devices ==")
        csrf = await get_csrf(client)
        devices = []
        for i in range(3):
            device_id, api_key = await provision_device(
                client, csrf, f"load-test-{i}-{int(time.time())}"
            )
            devices.append((device_id, api_key))
            print(f"  device {device_id} provisioned")

        print("\n== Device auth checks ==")
        r = await client.post(
            "/api/v1/query",
            json={"query": "test"},
            headers={"X-Device-Key": "bogus-key-123"},
        )
        print(f"  bogus key -> {r.status_code} (expect 401)")

        revoke_id, revoke_key = devices[0]
        await revoke_device(client, csrf, revoke_id)
        r = await client.post(
            "/api/v1/query",
            json={"query": "test"},
            headers={"X-Device-Key": revoke_key},
        )
        print(f"  revoked key -> {r.status_code} (expect 401)")

        good_devices = devices[1:]

        print("\n== Concurrency: baseline single request ==")
        _, status, dt_single = await timed_query(
            client, good_devices[0][1], "What is gravity?", "baseline"
        )
        print(f"  single request: {dt_single:.2f}s (status {status})")

        print("\n== Concurrency: 4 concurrent requests + a health check mid-flight ==")

        async def health_probe():
            await asyncio.sleep(max(dt_single * 0.3, 0.05))
            t0 = time.monotonic()
            r = await client.get("/health")
            return time.monotonic() - t0, r.status_code

        query_tasks = [
            timed_query(
                client,
                good_devices[i % len(good_devices)][1],
                f"What is energy? (request {i})",
                f"concurrent-{i}",
            )
            for i in range(4)
        ]
        query_results, (health_dt, health_status) = await asyncio.gather(
            asyncio.gather(*query_tasks), health_probe()
        )
        slowest = max(dt for _, _, dt in query_results)
        serial_estimate = dt_single * len(query_results)
        print(f"  {len(query_results)} concurrent requests, slowest: {slowest:.2f}s")
        print(
            f"  if the event loop were blocked, this would take roughly "
            f"{serial_estimate:.2f}s (serial) instead"
        )
        print(f"  /health responded in {health_dt:.3f}s (status {health_status}) DURING that load")

        print("\n== Voice endpoint concurrency cap (default MAX_CONCURRENT_VOICE_REQUESTS=4) ==")
        wav_bytes = make_silence_wav()

        async def voice_call(i: int):
            files = {"audio": (f"test{i}.wav", wav_bytes, "audio/wav")}
            data = {"session_id": f"sim-session-{i}"}
            t0 = time.monotonic()
            r = await client.post(
                "/api/v1/voice/query",
                files=files,
                data=data,
                headers={"X-Device-Key": good_devices[0][1]},
            )
            return i, r.status_code, time.monotonic() - t0

        voice_results = await asyncio.gather(
            *(voice_call(i) for i in range(6)), return_exceptions=True
        )
        for r in voice_results:
            if isinstance(r, tuple):
                print(f"    request {r[0]}: status {r[1]} ({r[2]:.2f}s)")
            else:
                print(f"    request errored: {r!r}")
        busy = [r for r in voice_results if isinstance(r, tuple) and r[1] == 503]
        print(f"  fired 6 concurrent voice requests against a cap of 4 -> {len(busy)} got 503 'busy'")

        print("\n== Cleanup ==")
        for device_id, _ in good_devices:
            await revoke_device(client, csrf, device_id)
        print("  test devices revoked")


if __name__ == "__main__":
    asyncio.run(main())
