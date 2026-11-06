#!/usr/bin/env python3
"""Build a self-contained dark HTML evidence report from LAMDA artifacts.

Inputs can be:
  * a single capture directory containing screen.jpg / window.xml / meta.json
  * a run directory containing case subdirectories
  * a run directory containing summary.json (sdk-autotest compatible)

The output contains only static HTML/CSS and copied evidence files. It does not
read .env or make network calls.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(line_buffering=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
EVIDENCE_EXT = IMAGE_EXT | {".xml", ".json", ".txt", ".log"}
IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def slug(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return cleaned[:80] or "case"


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def fmt_ms(value: Any) -> str:
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{ms / 1000:.2f}s" if ms >= 1000 else f"{ms:.1f}ms"


def fmt_cny(value: Any) -> str:
    try:
        return f"¥{float(value):.6f}"
    except (TypeError, ValueError):
        return "—"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def optional_json(path: Path) -> Any:
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def evidence_files(directory: Path | None) -> list[Path]:
    if directory is None or not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in EVIDENCE_EXT
    )


def find_case_dir(root: Path, name: str) -> Path | None:
    direct = root / slug(name)
    if direct.is_dir():
        return direct
    target = slug(name)
    for path in root.iterdir():
        if path.is_dir() and slug(path.name) == target:
            return path
    return None


def discover_cases(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = optional_json(root / "summary.json")
    if isinstance(summary, dict) and summary.get("cases"):
        cases = []
        for case in summary["cases"]:
            name = str(case.get("name", "case"))
            cases.append(
                {
                    **case,
                    "name": name,
                    "dir": find_case_dir(root, name),
                }
            )
        return cases, summary

    # No summary: treat each child directory with evidence as a captured case.
    cases = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if evidence_files(child):
            cases.append(
                {
                    "name": child.name,
                    "status": "captured",
                    "duration_ms": None,
                    "ai_calls": 0,
                    "tokens": 0,
                    "cost_cny": 0.0,
                    "dir": child,
                }
            )
    if not cases and evidence_files(root):
        cases.append(
            {
                "name": root.name,
                "status": "captured",
                "duration_ms": None,
                "ai_calls": 0,
                "tokens": 0,
                "cost_cny": 0.0,
                "dir": root,
            }
        )
    return cases, {}


def case_status(case: dict[str, Any], directory: Path | None) -> str:
    if directory is not None:
        failure = directory / "failure.json"
        if failure.exists():
            return "failed"
        timings = optional_json(directory / "timings.json")
        if isinstance(timings, dict) and timings.get("status"):
            return str(timings["status"])
    return str(case.get("status") or "unknown")


def case_duration(case: dict[str, Any], directory: Path | None) -> float | None:
    value = case.get("duration_ms")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    if directory is not None:
        timings = optional_json(directory / "timings.json")
        steps = (timings or {}).get("steps") or []
        if steps:
            return sum(float(step.get("ms") or 0) for step in steps)
    return None


def case_oracles(directory: Path | None) -> list[dict[str, Any]]:
    if directory is None:
        return []
    out = []
    for path in sorted(directory.glob("*oracle*.json")):
        data = optional_json(path) or {}
        response = data.get("response") or {}
        request = data.get("request") or {}
        passed = response.get("pass")
        expected_reject = passed is False and "negative" in path.stem.lower()
        if passed is True:
            label, kind = "通过", "pass"
        elif expected_reject:
            label, kind = "拒绝（预期）", "warn"
        elif passed is False:
            label, kind = "拒绝", "fail"
        else:
            label, kind = "未知", "warn"
        out.append(
            {
                "file": path.name,
                "mode": request.get("mode", "assert"),
                "prompt": request.get("prompt", ""),
                "pass": passed,
                "label": label,
                "kind": kind,
                "thought": response.get("thought") or "",
                "duration_ms": response.get("duration_ms"),
            }
        )
    return out


def case_failure(directory: Path | None) -> str | None:
    if directory is None:
        return None
    data = optional_json(directory / "failure.json")
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return None


def case_note(directory: Path | None) -> str:
    if directory is None:
        return ""
    for name in ("meta.json", "deterministic.json"):
        data = optional_json(directory / name)
        if not isinstance(data, dict):
            continue
        note = data.get("note")
        if not note and isinstance(data.get("notes"), list):
            note = "; ".join(str(item) for item in data["notes"])
        if note:
            return str(note)
    return ""


def case_analysis(directory: Path | None) -> str:
    if directory is None:
        return ""
    for name in ("analysis.md", "analysis.txt"):
        path = directory / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                pass
    for name in ("meta.json", "deterministic.json"):
        data = optional_json(directory / name)
        if isinstance(data, dict):
            value = data.get("analysis") or data.get("opinion")
            if value:
                return str(value)
    return ""


def case_steps(directory: Path | None) -> list[dict[str, Any]]:
    if directory is None:
        return []
    data = optional_json(directory / "timings.json") or {}
    return data.get("steps") or []


def copy_evidence(directory: Path | None, destination: Path) -> list[Path]:
    if directory is None:
        return []
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in evidence_files(directory):
        target = destination / path.name
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def data_uri(path: Path) -> str:
    mime = IMAGE_MIME.get(path.suffix.lower(), "application/octet-stream")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_oracles(oracles: list[dict[str, Any]]) -> str:
    if not oracles:
        return ""
    rows = []
    thoughts = []
    for item in oracles:
        rows.append(
            "<tr>"
            f"<td>{esc(item['file'])}</td>"
            f"<td>{esc(item['mode'])}</td>"
            f"<td><span class='badge b-{esc(item['kind'])}'>{esc(item['label'])}</span></td>"
            f"<td class='num'>{fmt_ms(item.get('duration_ms'))}</td>"
            "</tr>"
        )
        if item["thought"]:
            thoughts.append(
                f"<div class='thought'><b>{esc(item['file'])}</b>："
                f"{esc(item['thought'])}</div>"
            )
    return (
        "<h4>Oracle</h4>"
        "<div class='tblwrap'><table><thead><tr>"
        "<th>文件</th><th>模式</th><th>结果</th><th class='num'>耗时</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        + "".join(thoughts)
    )


def render_steps(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return ""
    rows = []
    for index, step in enumerate(steps, 1):
        ok = step.get("ok", True)
        badge = "<span class='ok'>done</span>" if ok else "<span class='bad'>fail</span>"
        rows.append(
            f"<tr id='step-{index}'>"
            f"<td>{esc(step.get('name'))}</td>"
            f"<td>{esc(step.get('kind'))}</td>"
            f"<td class='num'>{fmt_ms(step.get('ms'))}</td>"
            f"<td>{badge}</td>"
            "</tr>"
        )
    total = sum(float(step.get("ms") or 0) for step in steps)
    return (
        f"<h4>步骤耗时 <span class='muted'>{len(steps)} 步 · 合计 {fmt_ms(total)}</span></h4>"
        "<div class='tblwrap'><table><thead><tr>"
        "<th>步骤</th><th>类型</th><th class='num'>耗时</th><th>结果</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_json_block(path: Path) -> str:
    data = optional_json(path)
    if data is None:
        return ""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        f"<details class='json'><summary>{esc(path.name)}</summary>"
        f"<pre>{esc(text[:50000])}</pre></details>"
    )


def render_xml_block(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return (
        f"<details class='json'><summary>{esc(path.name)} · {len(text):,} chars</summary>"
        f"<pre>{esc(text[:30000])}</pre></details>"
    )


def render_case(
    case: dict[str, Any],
    directory: Path | None,
    evidence_out: Path,
    asset_prefix: str = "",
) -> str:
    status = case_status(case, directory)
    kind = "pass" if status == "passed" else (
        "fail" if status in {"failed", "error"} else "warn"
    )
    duration = case_duration(case, directory)
    oracles = case_oracles(directory)
    steps = case_steps(directory)
    failure = case_failure(directory)
    note = case_note(directory)
    analysis = case_analysis(directory)
    copied = copy_evidence(directory, evidence_out)

    images = [path for path in copied if path.suffix.lower() in IMAGE_EXT]
    other = [path for path in copied if path.suffix.lower() not in IMAGE_EXT]

    shots = []
    for path in images:
        shots.append(
            "<figure class='shot'>"
            f"<a href='{asset_prefix}files/{esc(evidence_out.name)}/{esc(path.name)}' target='_blank'>"
            f"<img src='{data_uri(path)}' alt='{esc(path.name)}' loading='lazy'></a>"
            f"<figcaption>{esc(path.name)}</figcaption></figure>"
        )

    json_blocks = []
    for path in other:
        if path.suffix.lower() == ".xml":
            json_blocks.append(render_xml_block(path))
        elif path.suffix.lower() == ".json":
            json_blocks.append(render_json_block(path))

    links = "".join(
        f"<a class='link' href='{asset_prefix}files/{esc(evidence_out.name)}/{esc(path.name)}' "
        f"target='_blank' rel='noopener'>{esc(path.name)} ↗</a>"
        for path in copied
    )

    failure_html = (
        f"<div class='failure'><b>失败信息</b><pre>{esc(failure[-8000:])}</pre></div>"
        if failure
        else ""
    )
    shots_html = f"<div class='shots'>{''.join(shots)}</div>" if shots else ""
    links_html = f"<div class='links'>{links}</div>" if links else ""
    note_html = f"<div class='case-note'>{esc(note)}</div>" if note else ""
    analysis_html = (
        "<div class='analysis'><h4>解析意见 / 分析意见</h4>"
        f"<div class='analysis-text'>{esc(analysis)}</div></div>"
        if analysis
        else ""
    )
    meta = (
        f"{esc(status)} · {fmt_ms(duration)} · "
        f"{fmt_int(case.get('ai_calls', 0))} AI · "
        f"{fmt_int(case.get('tokens', 0))} tokens · "
        f"{fmt_cny(case.get('cost_cny', 0))}"
    )

    return f"""
    <article class='case'>
      <header class='case-head'>
        <div>
          <div class='case-name'>{esc(case.get('name'))}</div>
          <div class='case-meta'>{meta}</div>
        </div>
        <span class='badge b-{kind}'>{esc(status.upper())}</span>
      </header>
      {note_html}
      {analysis_html}
      {failure_html}
      {shots_html}
      {render_oracles(oracles)}
      {render_steps(steps)}
      {''.join(json_blocks)}
      {links_html}
    </article>"""


def _status_kind(status: str) -> str:
    if status == "passed":
        return "pass"
    if status in {"failed", "error"}:
        return "fail"
    return "warn"


def _status_badge(status: str) -> str:
    return (
        f"<span class='badge b-{_status_kind(status)}'>"
        f"{esc(status.upper())}</span>"
    )


def render_index_rows(cases: list[dict[str, Any]]) -> str:
    rows = []
    for case in cases:
        directory = case.get("dir")
        name = str(case.get("name", "case"))
        status = case_status(case, directory)
        note = case_note(directory)
        detail = f"cases/{slug(name)}.html"
        steps = case_steps(directory)
        case_badge = _status_badge(status)
        note_html = f"<div class='case-meta'>{esc(note)}</div>" if note else ""

        if not steps:
            rows.append(
                "<tr>"
                f"<td><div class='case-name'>{esc(name)}</div>{note_html}</td>"
                "<td>—</td><td>—</td>"
                f"<td class='num'>{fmt_ms(case_duration(case, directory))}</td>"
                "<td>—</td>"
                f"<td>{case_badge}</td>"
                f"<td><a class='link' href='{esc(detail)}'>打开详情 →</a></td>"
                "</tr>"
            )
            continue

        for index, step in enumerate(steps, 1):
            step_ok = step.get("ok", True)
            step_badge = (
                "<span class='badge b-pass'>DONE</span>"
                if step_ok
                else "<span class='badge b-fail'>FAIL</span>"
            )
            rows.append(
                "<tr>"
                f"<td><div class='case-name'>{esc(name)}</div>{note_html}</td>"
                f"<td>{esc(step.get('name'))}</td>"
                f"<td>{esc(step.get('kind'))}</td>"
                f"<td class='num'>{fmt_ms(step.get('ms'))}</td>"
                f"<td>{step_badge}</td>"
                f"<td>{case_badge}</td>"
                f"<td><a class='link' href='{esc(detail)}#step-{index}'>打开详情 →</a></td>"
                "</tr>"
            )
    return "".join(rows)


def render_detail_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · 详情</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <a class="chip" href="../index.html">← 返回总览</a>
  {body}
</div>
</body>
</html>"""


CSS = """
:root {
  --bg: #0b1220; --panel: #111b2e; --panel2: #16233a; --border: #243653;
  --fg: #e8eef8; --fg2: #a9b8cf; --fg3: #7185a3;
  --green: #43d17a; --red: #ff6b6b; --amber: #f3b34c; --blue: #6aa8ff;
  --radius: 12px;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.wrap { max-width: 1240px; margin: 0 auto; padding: 40px 28px 72px; }
.kicker { color: var(--blue); font-size: 12px; letter-spacing: .14em; font-weight: 700; }
h1 { font-size: 38px; line-height: 1.15; margin: 8px 0 10px; }
.lede { color: var(--fg2); margin: 0; max-width: 860px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.chip, .link {
  border: 1px solid var(--border); background: var(--panel);
  color: var(--fg2); border-radius: 999px; padding: 5px 11px;
  font-size: 12px; text-decoration: none;
}
.chip:hover, .link:hover { border-color: var(--blue); color: var(--fg); }
.sec-head { display: flex; align-items: baseline; gap: 10px; margin: 28px 0 10px; }
.sec-head h2 { font-size: 20px; margin: 0; }
.sec-head .hint { color: var(--fg3); font-size: 12px; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 26px 0 30px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.card .k { color: var(--fg3); font-size: 12px; }
.card .v { font-size: 28px; font-weight: 700; margin-top: 4px; }
.card .s { color: var(--fg3); font-size: 12px; margin-top: 2px; }
.case {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px; margin: 16px 0;
}
.case-head { display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; }
.case-name { font-size: 17px; font-weight: 700; overflow-wrap: anywhere; }
.case-meta { color: var(--fg3); font-size: 12px; margin-top: 4px; }
.case-note { color: var(--fg2); font-size: 12px; margin-top: 10px; padding: 7px 10px; background: var(--panel2); border-left: 2px solid var(--amber); border-radius: 0 6px 6px 0; }
.analysis { margin-top: 12px; padding: 10px 12px; border: 1px solid rgba(243,179,76,.35); background: rgba(243,179,76,.06); border-radius: 8px; }
.analysis h4 { margin: 0 0 6px; color: var(--amber); }
.analysis-text { color: var(--fg2); font-size: 12px; line-height: 1.7; white-space: pre-wrap; }
.badge { display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700; }
.b-pass { color: var(--green); background: rgba(67,209,122,.12); border: 1px solid rgba(67,209,122,.35); }
.b-fail { color: var(--red); background: rgba(255,107,107,.12); border: 1px solid rgba(255,107,107,.35); }
.b-warn { color: var(--amber); background: rgba(243,179,76,.12); border: 1px solid rgba(243,179,76,.35); }
h4 { color: var(--fg2); font-size: 13px; margin: 18px 0 8px; }
.muted { color: var(--fg3); font-weight: 400; }
.tblwrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; min-width: 560px; }
.t-steps { min-width: 980px; }
.t-steps .case-name { font-size: 13px; }
.t-steps .case-meta { margin-top: 2px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
th { color: var(--fg3); background: var(--panel2); }
tr:last-child td { border-bottom: 0; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.ok { color: var(--green); } .bad { color: var(--red); }
.shots { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-top: 14px; }
.shot { margin: 0; background: #0a101b; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.shot img { display: block; width: 100%; height: auto; }
.shot figcaption { padding: 7px 10px; color: var(--fg3); font-size: 11px; }
.thought { margin: 8px 0; padding: 9px 11px; background: var(--panel2); border-left: 2px solid var(--blue); color: var(--fg2); font-size: 12px; }
.failure { margin-top: 14px; padding: 12px; border: 1px solid rgba(255,107,107,.35); background: rgba(255,107,107,.08); border-radius: 10px; }
.failure b { color: var(--red); }
pre { margin: 8px 0 0; padding: 10px; background: #080d16; border: 1px solid var(--border); border-radius: 8px; overflow: auto; max-height: 360px; color: #cdd8ea; font-size: 11px; }
details.json { margin-top: 10px; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }
details.json summary { cursor: pointer; color: var(--fg2); font-size: 12px; }
.links { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.note { color: var(--fg3); font-size: 12px; margin-top: 22px; }
@media (max-width: 900px) { .cards { grid-template-columns: repeat(2, 1fr); } .shots { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .cards, .shots { grid-template-columns: 1fr; } h1 { font-size: 30px; } .wrap { padding: 28px 18px 48px; } }
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="capture/run directory")
    parser.add_argument("--out", default="report", help="output report directory")
    parser.add_argument("--title", default=None, help="report title")
    parser.add_argument(
        "--subtitle",
        default="LAMDA 截图 / XML / oracle 证据",
        help="report subtitle",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the report after building (blocks until Ctrl-C)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8914,
        help="port for --serve (default: 8914)",
    )
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="bind address for --serve (use 0.0.0.0 for LAN)",
    )
    args = parser.parse_args()

    root = Path(args.input)
    if not root.exists():
        print(f"input not found: {root}", file=sys.stderr)
        return 2
    out = Path(args.out)
    if out.resolve() == root.resolve():
        print("--out must not be the input directory", file=sys.stderr)
        return 2
    if out.exists():
        shutil.rmtree(out)
    files_root = out / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    protocol_html = ""

    cases, summary = discover_cases(root)
    if not cases:
        print(f"no evidence found in {root}", file=sys.stderr)
        return 1

    detail_dir = out / "cases"
    detail_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        directory = case.get("dir")
        raw_name = str(case.get("name", "case"))
        name = slug(raw_name)
        body = render_case(
            case,
            directory,
            files_root / name,
            asset_prefix="../",
        )
        detail_dir.joinpath(f"{name}.html").write_text(
            render_detail_page(raw_name, body), encoding="utf-8"
        )
    step_rows = render_index_rows(cases)

    statuses = [case_status(case, case.get("dir")) for case in cases]
    passed = sum(1 for status in statuses if status == "passed")
    failed = sum(1 for status in statuses if status in {"failed", "error"})
    captured = sum(1 for status in statuses if status == "captured")
    blocked = sum(1 for status in statuses if status == "blocked")
    skipped = sum(1 for status in statuses if status == "skipped")
    totals = summary.get("totals") or {}
    duration = totals.get("wall_ms")
    if duration is None:
        durations = [
            case_duration(case, case.get("dir")) for case in cases
        ]
        present = [value for value in durations if value is not None]
        duration = sum(present) if present else None
    screenshots = sum(
        1
        for case in cases
        for path in evidence_files(case.get("dir"))
        if path.suffix.lower() in IMAGE_EXT
    )
    ai_calls = totals.get("ai_calls")
    if ai_calls is None:
        ai_calls = sum(int(case.get("ai_calls") or 0) for case in cases)
    tokens = totals.get("total_tokens")
    if tokens is None:
        tokens = sum(int(case.get("tokens") or 0) for case in cases)
    cost = totals.get("cost_cny")
    if cost is None:
        cost = sum(float(case.get("cost_cny") or 0) for case in cases)

    title = args.title or f"LAMDA 报告 · {root.name}"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cards = [
        (
            "用例",
            f"{len(cases)}",
            f"{passed} passed · {failed} failed · {captured} captured · "
            f"{blocked} blocked · {skipped} skipped",
        ),
        ("耗时", fmt_ms(duration), "cases 合计"),
        ("截图", f"{screenshots}", "已内嵌"),
        ("AI", fmt_int(ai_calls), f"{fmt_int(tokens)} tokens · {fmt_cny(cost)}"),
    ]
    cards_html = "".join(
        f"<div class='card'><div class='k'>{esc(k)}</div><div class='v'>{esc(v)}</div><div class='s'>{esc(s)}</div></div>"
        for k, v, s in cards
    )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="kicker">LAMDA EVIDENCE REPORT</div>
  <h1>{esc(title)}</h1>
  <p class="lede">{esc(args.subtitle)}</p>
  <div class="meta">
    <span class="chip">{esc(generated)}</span>
    <span class="chip">input: {esc(root)}</span>
    <span class="chip">static · no external assets</span>
  </div>
  <div class="cards">{cards_html}</div>
  <section>
    <div class="sec-head">
      <h2>步骤 / 用例</h2>
      <span class="hint">点击“打开详情”查看截图、XML、timings、oracle 和失败信息</span>
    </div>
    <div class="tblwrap">
      <table class="t-steps">
        <thead>
          <tr>
            <th>用例 / 备注</th><th>步骤</th><th>类型</th>
            <th class="num">耗时</th><th>步骤执行</th><th>用例状态</th><th>详情</th>
          </tr>
        </thead>
        <tbody>{step_rows}</tbody>
      </table>
    </div>
  </section>
{protocol_html}
  <p class="note">报告可能包含手机屏幕、账号/手机号等敏感信息；只服务本目录，限制访问。截图已内嵌，原始 XML/JSON 在 files/ 下。</p>
</div>
</body>
</html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"report: {(out / 'index.html').resolve()}")
    print(f"cases : {len(cases)} · screenshots: {screenshots}")

    if args.serve:
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        class ReportServer(ThreadingHTTPServer):
            allow_reuse_address = True

        handler = partial(
            SimpleHTTPRequestHandler, directory=str(out.resolve())
        )
        try:
            httpd = ReportServer((args.bind, args.port), handler)
        except OSError as exc:
            print(f"cannot serve on {args.bind}:{args.port}: {exc}", file=sys.stderr)
            return 1
        shown = "127.0.0.1" if args.bind == "0.0.0.0" else args.bind
        print(f"serve : http://{shown}:{args.port}/")
        print("stop  : Ctrl-C")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
