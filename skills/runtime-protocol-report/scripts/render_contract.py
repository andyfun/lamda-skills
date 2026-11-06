#!/usr/bin/env python3
"""Render contract.json into contract.md and a standalone index.html."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def render_md(c: dict, title: str, subtitle: str) -> str:
    lines = [f"# {title}", ""]
    if subtitle:
        lines += [subtitle, ""]
    lines += [
        f"- generated: `{c['generated_at']}`",
        f"- source: `{c.get('source', 'n/a')}`",
        f"- flows: **{c['flow_count']}** → endpoints: **{len(c['endpoints'])}**",
        f"- redacted: **{c['redacted']}**",
        "",
        "## Endpoints",
        "",
        "| Method | Endpoint | Content-Type | Status | Codes | Flags |",
        "|---|---|---|---|---|---|",
    ]
    for e in c["endpoints"]:
        codes = ", ".join(e["business_codes"].keys()) or "—"
        lines.append(
            f"| {'/'.join(e['methods'])} | `{e['endpoint']}` | "
            f"{e.get('request_content_type') or '—'} | "
            f"{'/'.join(str(s) for s in e['response_statuses']) or '—'} | {codes} | "
            f"{', '.join(e['flags']) or '—'} |"
        )

    lines += ["", "## Details", ""]
    for e in c["endpoints"]:
        lines += [f"### `{e['endpoint']}`", ""]
        lines.append(f"`{e['url']}` · {e['observed']} call{'s' if e['observed'] != 1 else ''}")
        lines.append("")
        if e["common_fields"]:
            lines.append(f"- common fields: {', '.join('`%s`' % f for f in e['common_fields'])}")
        if e["business_fields"]:
            lines.append(f"- business fields: {', '.join('`%s`' % f for f in e['business_fields'])}")
        if e.get("request_sample"):
            lines.append("- request sample:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(e["request_sample"], ensure_ascii=False, indent=2))
            lines.append("```")
        if e.get("response_shape"):
            lines.append("- response shape:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(e["response_shape"], ensure_ascii=False, indent=2))
            lines.append("```")
        if e["business_codes"]:
            pairs = ", ".join(f"{k} → {v}" for k, v in e["business_codes"].items())
            lines.append(f"- business codes: {pairs}")
        lines.append("")

    if c["business_codes"]:
        lines += ["## Error codes", "", "| code | message |", "|---|---|"]
        for k, v in c["business_codes"].items():
            lines.append(f"| {k} | {v or ''} |")
        lines.append("")

    if c["signature_candidates"]:
        lines += [
            "## Signature candidates",
            "",
            ", ".join("`%s`" % s for s in c["signature_candidates"]),
            "",
            "A `sign` field being present does not prove it is verified. Recompute it against a"
            " captured value before claiming the scheme is confirmed.",
            "",
        ]

    if not c["redacted"]:
        lines += [
            "> **Warning**: rendered without redaction. This document contains PII.",
            "",
        ]
    return "\n".join(lines)


def render_html(c: dict, title: str, subtitle: str) -> str:
    def esc(x):
        return html.escape(str(x))

    rows = []
    for e in c["endpoints"]:
        codes = ", ".join(e["business_codes"].keys()) or "—"
        flags = "".join(f'<span class="flag">{esc(f)}</span>' for f in e["flags"]) or "—"
        rows.append(
            "<tr>"
            f"<td class='m'>{esc('/'.join(e['methods']))}</td>"
            f"<td class='p'><code>{esc(e['endpoint'])}</code></td>"
            f"<td class='ct'>{esc(e.get('request_content_type') or '—')}</td>"
            f"<td>{esc('/'.join(str(s) for s in e['response_statuses']) or '—')}</td>"
            f"<td>{esc(codes)}</td>"
            f"<td>{flags}</td>"
            "</tr>"
        )

    cards = []
    for e in c["endpoints"]:
        sample = json.dumps(e["request_sample"], ensure_ascii=False, indent=2) if e.get("request_sample") else "—"
        shape = json.dumps(e["response_shape"], ensure_ascii=False, indent=2) if e.get("response_shape") else "—"
        codes = "".join(
            f"<div class='kv'><b>{esc(k)}</b><span>{esc(v or '')}</span></div>"
            for k, v in e["business_codes"].items()
        ) or "<span class='muted'>none observed</span>"
        cards.append(
            "<details class='card'>"
            f"<summary><span class='m'>{esc('/'.join(e['methods']))}</span>"
            f"<code>{esc(e['endpoint'])}</code><span class='n'>{e['observed']} call{'s' if e['observed'] != 1 else ''}</span></summary>"
            "<div class='grid'>"
            f"<div><h4>Request sample</h4><pre>{esc(sample)}</pre></div>"
            f"<div><h4>Response shape</h4><pre>{esc(shape)}</pre></div>"
            "</div>"
            f"<h4>Business codes</h4><div class='codes'>{codes}</div>"
            f"<h4>Headers</h4><pre>{esc(json.dumps(e['request_headers'], ensure_ascii=False, indent=2))}</pre>"
            "</details>"
        )

    errors = "".join(
        f"<div class='kv'><b>{esc(k)}</b><span>{esc(v or '')}</span></div>"
        for k, v in c["business_codes"].items()
    ) or "<span class='muted'>none observed</span>"

    warning = (
        ""
        if c["redacted"]
        else "<div class='warn'>Rendered without redaction — this page contains PII. Do not share.</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
:root{{--bg:#0b0f16;--panel:#121823;--line:#233046;--text:#e6edf7;--muted:#8b9bb4;--accent:#4c9aff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,"PingFang SC",system-ui,sans-serif}}
header{{padding:26px 28px 18px;border-bottom:1px solid var(--line)}}
h1{{margin:0;font-size:19px}}
.sub{{color:var(--muted);font-size:12px;margin-top:4px}}
.stats{{display:flex;gap:26px;margin-top:16px;flex-wrap:wrap}}
.stats div b{{display:block;font-size:20px;line-height:1.1}}
.stats div span{{color:var(--muted);font-size:11px}}
main{{padding:20px 28px 60px;max-width:1200px}}
h2{{font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin:28px 0 10px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:500;font-size:12px}}
code{{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;color:#9ecbff;word-break:break-all}}
.m{{color:#7ee2a8;font-size:12px;font-weight:600;margin-right:6px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-bottom:10px;padding:0 14px}}
.card summary{{cursor:pointer;padding:12px 0;display:flex;gap:10px;align-items:center;list-style:none}}
.card summary::-webkit-details-marker{{display:none}}
.card .n{{margin-left:auto;color:var(--muted);font-size:11px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
h4{{margin:12px 0 6px;font-size:12px;color:var(--muted);font-weight:500}}
pre{{margin:0 0 10px;background:#0e131c;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;max-height:260px;font:12px ui-monospace,Menlo,monospace}}
.codes{{display:flex;flex-direction:column;gap:4px;font-size:12.5px}}
.kv{{display:flex;gap:10px}}
.kv b{{color:#ffd166;min-width:56px}}
.muted{{color:var(--muted)}}
.flag{{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;margin-right:4px;background:rgba(76,154,255,.12);color:#9ecbff;border:1px solid rgba(76,154,255,.25)}}
.warn{{margin:16px 28px;padding:10px 14px;border-radius:8px;background:rgba(220,38,38,.12);border:1px solid rgba(220,38,38,.35);color:#ff9b9b;font-size:13px}}
</style></head><body>
<header>
  <h1>{esc(title)}</h1>
  <div class="sub">{esc(subtitle) or 'runtime capture'} · generated {esc(c['generated_at'])} · source {esc(c.get('source','n/a'))}</div>
  <div class="stats">
    <div><b>{c['flow_count']}</b><span>flows</span></div>
    <div><b>{len(c['endpoints'])}</b><span>endpoints</span></div>
    <div><b>{len(c['hosts'])}</b><span>hosts</span></div>
    <div><b>{'yes' if c['redacted'] else 'NO'}</b><span>redacted</span></div>
  </div>
</header>
{warning}
<main>
  <h2>Endpoints</h2>
  <table><thead><tr><th>Method</th><th>Path</th><th>Content-Type</th><th>Status</th><th>Codes</th><th>Flags</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table>

  <h2>Error codes</h2>
  <div class="codes">{errors}</div>

  <h2>Details</h2>
  {''.join(cards)}
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description="Render contract.json into markdown + HTML")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Runtime protocol contract")
    ap.add_argument("--subtitle", default="")
    args = ap.parse_args()

    contract = json.loads(Path(args.contract).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    md = render_md(contract, args.title, args.subtitle)
    (out / "contract.md").write_text(md)

    page = render_html(contract, args.title, args.subtitle)
    (out / "index.html").write_text(page)

    print(f"written: {out / 'contract.md'}")
    print(f"written: {out / 'index.html'}  ({len(page)} bytes)")


if __name__ == "__main__":
    main()
