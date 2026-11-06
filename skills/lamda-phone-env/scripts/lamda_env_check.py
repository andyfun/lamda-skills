#!/usr/bin/env python3
"""Check LAMDA connectivity from a fresh computer.

No project files required. Requires only:
    pip install "lamda==10.9"

Examples:
    python lamda_env_check.py
    python lamda_env_check.py --out captures
    LAMDA_HOST=127.0.0.1 python lamda_env_check.py
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65000

# Keep stdout/stderr ordering stable when a caller merges them.
sys.stdout.reconfigure(line_buffering=True)


def _fail(message: str, hints: list[str] | None = None) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    for hint in hints or []:
        print(f"  - {hint}", file=sys.stderr)
    return 1


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
        help=f"LAMDA port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--certificate", help="optional lamda.pem")
    parser.add_argument("--quality", type=int, default=85, help="JPEG quality")
    parser.add_argument("--timeout", type=float, default=5.0, help="TCP timeout")
    parser.add_argument("--out", help="optional directory for screenshot + XML")
    parser.add_argument(
        "--allow-locked",
        action="store_true",
        help="capture even if the phone reports a locked screen",
    )
    args = parser.parse_args()

    target = f"{args.host}:{args.port}"
    print(f"target: {target}")

    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout):
            pass
    except OSError as exc:
        return _fail(
            f"TCP {target} unreachable: {exc}",
            [
                "Confirm the phone and this computer are on the same LAN/VPN.",
                "Check the phone IP; use the LAN IP, not 127.0.0.1.",
                "Check firewall, AP isolation, and whether LAMDA is running.",
            ],
        )
    print("tcp   : OK")

    try:
        from lamda.client import Device
    except ImportError:
        return _fail(
            "lamda client is not installed",
            ['pip install "lamda==10.9"'],
        )

    try:
        kwargs = {"port": args.port}
        if args.certificate:
            kwargs["certificate"] = args.certificate
        device = Device(args.host, **kwargs)
        server = device.server_info()
        current = device.current_application()
        screen_on = device.is_screen_on()
        if not screen_on:
            device.wake_up()
            time.sleep(0.5)
            screen_on = device.is_screen_on()
        locked = device.is_screen_locked()
        package = getattr(current, "applicationId", None) or str(current)
        version = str(getattr(server, "version", "unknown"))
        architecture = str(getattr(server, "architecture", "unknown"))
    except Exception as exc:
        text = str(exc)
        hints = [
            "Confirm LAMDA/FIRERPA is running on the phone.",
            "Confirm the port and whether certificate/TLS is enabled.",
            "If the phone is reachable with nc but not Python, check the "
            "computer's local-network/firewall permissions.",
        ]
        if "cert" in text.lower() or "tls" in text.lower():
            hints.insert(0, "Pass --certificate /path/to/lamda.pem")
        return _fail(f"LAMDA connection failed: {exc}", hints)

    print(f"server: {version} ({architecture})")
    print(f"app   : {package}")
    print(f"screen: on={screen_on} locked={locked}")

    if not screen_on:
        return _fail(
            "screen is still off after wake_up",
            ["Turn the phone screen on manually, then rerun."],
        )

    if locked and not args.allow_locked:
        return _fail(
            "phone screen is locked",
            ["Unlock the phone, keep it awake, then rerun."],
        )

    try:
        screenshot = device.screenshot(args.quality).getvalue()
        xml = device.dump_window_hierarchy().getvalue()
    except Exception as exc:
        return _fail(
            f"screenshot/XML failed: {exc}",
            ["Unlock the phone and avoid secure/black screens."],
        )

    if len(screenshot) < 10_000:
        return _fail(
            f"screenshot is too small ({len(screenshot)} bytes)",
            ["The screen may be black, locked, or a secure surface."],
        )
    if b"<hierarchy" not in xml:
        return _fail("window hierarchy does not look like Android XML")

    print(f"shot  : {len(screenshot)} bytes")
    print(f"xml   : {len(xml)} bytes")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "screen.jpg").write_bytes(screenshot)
        (out / "window.xml").write_bytes(xml)
        (out / "meta.json").write_text(
            json.dumps(
                {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "host": args.host,
                    "port": args.port,
                    "server": version,
                    "architecture": architecture,
                    "current_app": package,
                    "screen_on": screen_on,
                    "locked": locked,
                    "screenshot_bytes": len(screenshot),
                    "xml_bytes": len(xml),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"saved : {out.resolve()}")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
