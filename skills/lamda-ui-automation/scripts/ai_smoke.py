#!/usr/bin/env python3
"""Rooted-device AI smoke runner for opaque (Unity/Flutter/canvas) apps.

The runner is intentionally app-agnostic. It provides primitives:

  wait / capture / tap / probe / assert

The caller supplies a JSON config with a `steps` list. The visual oracle is
read-only (static screenshot, actionSpace=[]); taps are deterministic
coordinates from the config, never model actions.

Example:
    ai_smoke.py --app <pkg> --activity <pkg/activity> \
      --config smoke.json --out artifacts/run

Config:
{
  "steps": [
    {"type": "wait", "seconds": 15},
    {"type": "capture", "name": "step_01"},
    {"type": "probe", "name": "loading", "prompt": "...",
     "if_true": [{"type": "wait", "seconds": 10},
                 {"type": "capture", "name": "step_01"}]},
    {"type": "probe", "name": "auth", "prompt": "...",
     "if_true": [{"type": "tap", "x": 100, "y": 200},
                 {"type": "wait", "seconds": 3}]},
    {"type": "assert", "name": "final", "prompt": "..."}
  ]
}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)


def load_env(path: Path) -> dict[str, str]:
    env = os.environ.copy()
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_config(path: str | None) -> dict:
    if not path:
        return {}
    data = json.loads(Path(path).expanduser().read_text())
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Best-effort JPEG SOF parser; avoids Pillow as a dependency."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9):
            continue
        if i + 2 > len(data):
            break
        length = int.from_bytes(data[i : i + 2], "big")
        if length < 2:
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 7 > len(data):
                break
            height = int.from_bytes(data[i + 3 : i + 5], "big")
            width = int.from_bytes(data[i + 5 : i + 7], "big")
            return width, height
        i += length
    return None


def point(value) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return int(value[0]), int(value[1])
    if isinstance(value, str) and "," in value:
        x, y = value.split(",", 1)
        return int(x), int(y)
    raise ValueError(f"invalid point: {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("LAMDA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LAMDA_PORT", "65000")))
    parser.add_argument("--certificate", default=None)
    parser.add_argument("--app", required=True)
    parser.add_argument("--activity", default=None, help="component for am start -n")
    parser.add_argument("--out", required=True, help="run directory")
    parser.add_argument("--case", default="ai_smoke", help="case subdirectory")
    parser.add_argument("--config", default=None, help="JSON steps config")
    parser.add_argument("--oracle", default="oracle/oracle.mjs")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--wait", type=float, default=5.0, help="default post-start wait")
    parser.add_argument("--root-setup", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--cold-start", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    try:
        from lamda.client import Device, protos
    except ImportError as exc:
        raise SystemExit(
            "lamda client not installed in this interpreter; use the venv Python "
            'with `pip install "lamda==10.9"`'
        ) from exc

    config = load_config(args.config)
    steps = config.get("steps")
    if steps is None:
        steps = [
            {"type": "wait", "seconds": args.wait},
            {"type": "capture", "name": "step_01"},
        ]
    if not isinstance(steps, list):
        raise SystemExit("config.steps must be a list")

    run = Path(args.out).expanduser()
    case = run / args.case
    case.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(args.env_file))
    oracle_path = Path(args.oracle)
    if not oracle_path.is_absolute():
        oracle_path = Path.cwd() / oracle_path

    kwargs = {"port": args.port}
    if args.certificate:
        kwargs["certificate"] = args.certificate
    d = Device(args.host, **kwargs)

    def sh(cmd: str, timeout: int = 60) -> str:
        result = d.execute_script(cmd, timeout=timeout)
        return (result.stdout or b"").decode("utf-8", "replace")

    def capture(name: str) -> Path:
        path = case / name
        path.write_bytes(d.screenshot(args.quality).getvalue())
        return path

    def run_oracle(screenshot: Path, mode: str, prompt: str, name: str) -> dict:
        if not oracle_path.exists():
            raise RuntimeError(f"oracle not found: {oracle_path}")
        data = screenshot.read_bytes()
        size = jpeg_size(data)
        if not size:
            raise RuntimeError(f"cannot determine JPEG size: {screenshot}")
        cmd = [
            "node", str(oracle_path),
            "--screenshot", str(screenshot),
            "--size", f"{size[0]}x{size[1]}",
            "--mode", mode,
            "--prompt", prompt,
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)
        (case / f"{name}.stdout.json").write_text(proc.stdout, encoding="utf-8")
        (case / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        line = next((x for x in reversed(proc.stdout.splitlines()) if x.strip().startswith("{")), None)
        if not line:
            raise RuntimeError(f"oracle returned no JSON ({name}): {proc.stdout[-400:]} {proc.stderr[-400:]}")
        result = json.loads(line)
        if not result.get("ok"):
            raise RuntimeError(f"oracle failed ({name}): {result}")
        (case / f"{name}.json").write_text(
            json.dumps(
                {
                    "request": {"mode": mode, "prompt": prompt, "screenshot": screenshot.name},
                    "response": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return result

    state: dict[str, object] = {"last_shot": None, "asserts": [], "probes": []}
    step_timings: list[dict] = []

    def exec_steps(items: list[dict]) -> None:
        for step in items:
            if not isinstance(step, dict):
                raise ValueError(f"invalid step: {step!r}")
            kind = step.get("type")
            label = str(step.get("name") or kind or "step")
            t = time.time()
            if kind == "wait":
                time.sleep(max(0.0, float(step.get("seconds", 1))))
            elif kind == "capture":
                state["last_shot"] = capture(str(step.get("name") or f"step_{len(step_timings)+1:02d}.jpg"))
            elif kind == "tap":
                pt = point([step.get("x"), step.get("y")])
                if not pt:
                    raise ValueError(f"tap step needs x/y: {step}")
                d.click(protos.Point(x=pt[0], y=pt[1]))
            elif kind == "probe":
                prompt = step.get("prompt")
                if not prompt:
                    raise ValueError(f"probe step needs prompt: {step}")
                shot_path = state.get("last_shot")
                if not isinstance(shot_path, Path) or not shot_path.exists():
                    shot_path = capture(f"{label}.jpg")
                    state["last_shot"] = shot_path
                result = run_oracle(shot_path, "boolean", str(prompt), f"probe_{label}")
                value = result.get("value") is True
                state["probes"].append({"name": label, "prompt": prompt, "value": value})
                branch = step.get("if_true") if value else step.get("if_false")
                if isinstance(branch, list):
                    exec_steps(branch)
            elif kind == "assert":
                prompt = step.get("prompt")
                if not prompt:
                    raise ValueError(f"assert step needs prompt: {step}")
                shot_path = state.get("last_shot")
                if not isinstance(shot_path, Path) or not shot_path.exists():
                    shot_path = capture(f"{label}.jpg")
                    state["last_shot"] = shot_path
                result = run_oracle(shot_path, "assert", str(prompt), f"oracle_{label}")
                passed = result.get("pass") is True
                state["asserts"].append({"name": label, "prompt": prompt, "pass": passed})
            else:
                raise ValueError(f"unknown step type: {kind}")
            step_timings.append({"name": label, "type": kind, "ms": int((time.time() - t) * 1000)})

    old: dict[str, str] = {}
    started = time.time()
    status = "captured"
    failure = None
    try:
        if args.root_setup:
            t = time.time()
            for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
                old[key] = sh(f"settings get global {key}").strip()
                sh(f"settings put global {key} 0")
            old["stayon"] = sh("settings get global stay_on_while_plugged_in").strip()
            sh("svc power stayon true")
            sh("logcat -c")
            step_timings.append({"name": "root_setup", "type": "setup", "ms": int((time.time() - t) * 1000)})

        if args.cold_start:
            t = time.time()
            sh(f"am force-stop {args.app}")
            if args.activity:
                sh(f"am start -W -n {args.activity}", timeout=90)
            else:
                sh(f"monkey -p {args.app} 1", timeout=90)
            step_timings.append({"name": "cold_start", "type": "setup", "ms": int((time.time() - t) * 1000)})

        exec_steps(steps)

        t = time.time()
        current = d.current_application().applicationId
        xml = d.dump_window_hierarchy().getvalue()
        (case / "window.xml").write_bytes(xml)
        (case / "logcat.txt").write_text(sh("logcat -d -v time -t 600", timeout=60))
        (case / "meminfo.txt").write_text(sh(f"dumpsys meminfo {args.app}", timeout=60))
        (case / "cpuinfo.txt").write_text(sh("dumpsys cpuinfo | head -40", timeout=60))
        (case / "activity.txt").write_text(
            sh("dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | head -5", timeout=60)
        )
        last_shot = state.get("last_shot")
        deterministic = {
            "app_foreground": current == args.app,
            "current_application": current,
            "screenshot_bytes": last_shot.stat().st_size if isinstance(last_shot, Path) and last_shot.exists() else 0,
            "xml_has_hierarchy": b"<hierarchy" in xml,
            "probes": state["probes"],
            "asserts": state["asserts"],
        }
        (case / "deterministic.json").write_text(json.dumps(deterministic, ensure_ascii=False, indent=2) + "\n")
        step_timings.append({"name": "collect_evidence", "type": "evidence", "ms": int((time.time() - t) * 1000)})

        asserts = state["asserts"]
        if not deterministic["app_foreground"]:
            status, failure = "failed", f"{args.app} is not foreground"
        elif not deterministic["xml_has_hierarchy"]:
            status, failure = "failed", "window hierarchy missing"
        elif any(not a["pass"] for a in asserts):
            status, failure = "failed", "one or more visual assertions failed"
        elif asserts:
            status = "passed"
        else:
            status = "captured"
    except Exception as exc:  # noqa: BLE001
        status, failure = "failed", str(exc)
        try:
            capture("failure.jpg")
            (case / "window.xml").write_bytes(d.dump_window_hierarchy().getvalue())
        except Exception:
            pass
    finally:
        if args.root_setup:
            try:
                for key, value in old.items():
                    if key == "stayon":
                        sh(f"settings put global stay_on_while_plugged_in {value or 0}")
                    else:
                        sh(f"settings put global {key} {value or 1}")
            except Exception as exc:  # noqa: BLE001
                print(f"teardown warning: {exc}", file=sys.stderr)

    probes = sorted(case.glob("probe_*.json")) + sorted(case.glob("oracle_*.json"))
    oracle_data = []
    for path in probes:
        try:
            oracle_data.append(json.loads(path.read_text())["response"])
        except Exception:
            pass

    def cost(usage: dict | None) -> float:
        if not usage:
            return 0.0
        pt = usage.get("prompt_tokens") or 0
        ct = usage.get("completion_tokens") or 0
        cached = usage.get("cached_tokens") or 0
        usd = ((max(pt - cached, 0) * 0.15) + (cached * 0.003) + (ct * 0.6)) / 1_000_000
        return usd * 7.1

    total_tokens = sum((o.get("usage") or {}).get("total_tokens") or 0 for o in oracle_data)
    total_cost = sum(cost(o.get("usage")) for o in oracle_data)
    wall_ms = int((time.time() - started) * 1000)
    if failure:
        (case / "failure.json").write_text(json.dumps({"error": failure}, ensure_ascii=False, indent=2) + "\n")

    (case / "meta.json").write_text(
        json.dumps({"app": args.app, "activity": args.activity, "host": args.host, "note": "generic AI smoke"}, ensure_ascii=False, indent=2) + "\n"
    )
    (case / "timings.json").write_text(json.dumps({"status": status, "steps": step_timings}, ensure_ascii=False, indent=2) + "\n")
    (case / "analysis.md").write_text(
        f"""# AI smoke · {args.app}

- Host: `{args.host}:{args.port}`
- Status: **{status}**
- Probes: {json.dumps(state['probes'], ensure_ascii=False)}
- Asserts: {json.dumps(state['asserts'], ensure_ascii=False)}
- AI calls: {len(oracle_data)} · tokens: {total_tokens} · estimated cost: ¥{total_cost:.6f}
- Failure: {failure or 'none'}

The visual oracle is read-only (`actionSpace=[]`, screenshot only). Taps are
deterministic coordinates from the config; the model never acts.
"""
    )
    (run / "summary.json").write_text(
        json.dumps(
            {
                "run_id": run.name,
                "device": {"product": args.host, "sdk": None},
                "cases": [{"name": args.case, "status": status, "duration_ms": wall_ms}],
                "totals": {"wall_ms": wall_ms, "ai_calls": len(oracle_data), "total_tokens": total_tokens, "cost_cny": round(total_cost, 8)},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"run": str(run), "status": status, "ai_calls": len(oracle_data), "tokens": total_tokens, "cost_cny": round(total_cost, 8)}, ensure_ascii=False, indent=2))
    return 0 if status in {"passed", "captured"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
