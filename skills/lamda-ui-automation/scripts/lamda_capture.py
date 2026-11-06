#!/usr/bin/env python3
"""Capture screenshot + XML for a LAMDA Android automation workflow.

Requires only:
    pip install "lamda==10.9"

Use this to prove the device/app/evidence path before writing a longer flow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65000

sys.stdout.reconfigure(line_buffering=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.environ.get("LAMDA_HOST", DEFAULT_HOST),
        help=f"phone LAN IP (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LAMDA_PORT", DEFAULT_PORT)),
    )
    parser.add_argument("--certificate", help="optional lamda.pem")
    parser.add_argument("--app", help="optional package to start/check")
    parser.add_argument("--out", default="captures", help="evidence directory")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--wait", type=float, default=2.0, help="app start wait")
    args = parser.parse_args()

    try:
        from lamda.client import Device
    except ImportError:
        raise SystemExit(
            "lamda client is not installed in this interpreter.\n"
            "Use the venv Python, e.g. "
            "$HOME/lamda-workspace/.venv/bin/python, and install "
            '"lamda==10.9".'
        )

    kwargs = {"port": args.port}
    if args.certificate:
        kwargs["certificate"] = args.certificate
    device = Device(args.host, **kwargs)

    current = device.current_application()
    print("current:", getattr(current, "applicationId", current))
    if not device.is_screen_on():
        device.wake_up()
        time.sleep(0.5)
    if not device.is_screen_on():
        raise SystemExit("screen is still off after wake_up; turn it on manually")
    if device.is_screen_locked():
        raise SystemExit("screen is locked; unlock the phone and rerun")

    if args.app:
        app = device.application(args.app)
        if not app.is_installed():
            raise SystemExit(f"{args.app} is not installed")
        app.start()
        time.sleep(max(0.0, args.wait))
        if not app.is_foreground():
            raise SystemExit(f"{args.app} is not in the foreground")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shot = device.screenshot(args.quality).getvalue()
    xml = device.dump_window_hierarchy().getvalue()
    if len(shot) < 10_000:
        raise SystemExit(
            f"screenshot is too small ({len(shot)} bytes); "
            "screen may be off, locked, or secure"
        )
    if b"<hierarchy" not in xml:
        raise SystemExit("window hierarchy does not look like Android XML")
    (out / "screen.jpg").write_bytes(shot)
    (out / "window.xml").write_bytes(xml)

    meta = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "port": args.port,
        "app": args.app,
        "current_app": getattr(
            device.current_application(), "applicationId", "unknown"
        ),
        "screen_on": device.is_screen_on(),
        "screenshot_bytes": len(shot),
        "xml_bytes": len(xml),
    }
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"saved: {out.resolve()}")
    print(f"shot : {len(shot)} bytes")
    print(f"xml  : {len(xml)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
