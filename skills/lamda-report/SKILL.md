---
name: lamda-report
description: Build a dark, self-contained HTML evidence report from LAMDA runs or captures (screenshots, XML, timings, oracle JSON, summary.json). Use when the user wants a test report/dashboard after phone automation, needs pass/fail and evidence review, or asks to package screenshots and XML into a shareable static page. Does not need the phone or an AI model.
---

# LAMDA Evidence Report

Generate a static report from evidence on disk. No phone connection, no model call, no `.env` access.

Building alone **does not start a server**. Add `--serve` to build and serve in one command.

## 1. Inputs

Accepted input shapes:

1. **Single capture**
   ```text
   captures/
   ├── screen.jpg
   ├── window.xml
   └── meta.json
   ```

2. **Run directory with case folders**
   ```text
   run/
   ├── test_login/
   │   ├── step_01.jpg
   │   ├── step_01.xml
   │   ├── deterministic.json
   │   └── timings.json
   └── test_user_center/
       └── ...
   ```

3. **sdk-autotest compatible run**
   ```text
   artifacts/<run_id>/
   ├── summary.json
   ├── junit.xml
   ├── report.html
   └── <case>/...
   ```

`summary.json` is optional. Without it, cases are marked `captured`; with it, status, duration, AI/tokens/cost and oracle stats are used.

## 2. Build

```bash
python scripts/build_report.py \
  --input captures \
  --out report \
  --title "手机截图报告"
```

For a test run:

```bash
python scripts/build_report.py \
  --input artifacts/20261026T104957Z-8ffb107-r1 \
  --out report
```

Generate and serve in one command:

```bash
python scripts/build_report.py \
  --input captures \
  --out report \
  --serve \
  --port 8914
```

`--serve` is optional and blocks until Ctrl-C. It defaults to `127.0.0.1`; use `--bind 0.0.0.0` only when LAN access is intended.

Output:

```text
report/
├── index.html              # summary + step/case list
├── cases/
│   └── <case>.html         # per-case detail page
└── files/
    └── <case>/
        ├── screen.jpg
        ├── window.xml
        └── ...
```

The index lists every case and its steps. Clicking **打开详情** opens the independent case page with screenshots, XML/JSON, timings, oracle results, and failure text.

Screenshots are embedded as data URIs. XML/JSON and other evidence are copied under `files/` and linked.

## 3. What the report shows

- Summary cards: cases, passed/failed/captured, duration, screenshots, AI/tokens/cost
- Per-case status badge and timing
- Embedded screenshots with captions
- Oracle table: pass / reject / expected negative reject / error
- Oracle thought text
- Step timing table
- `failure.json` error block
- **解析意见 / 分析意见** from optional `analysis.md`, `analysis.txt`, or an `analysis`/`opinion` field in `meta.json`
- Collapsible XML/JSON evidence
- Links to raw copied evidence

## 4. Status rules

1. `failure.json` exists → `failed`
2. `timings.json.status` present → use it
3. `summary.json` case status present → use it
4. Otherwise → `captured`

Do not call a captured screenshot “passed” unless an assertion or summary says so.

## 5. Serve and security

Either open the file directly:

```text
report/index.html
```

or serve it:

```bash
python scripts/build_report.py --input captures --out report --serve --port 8914
# or: python3 -m http.server 8914 --directory report
```

Then open `http://127.0.0.1:8914/`.

- Serve only the report directory, never the repo root or `.env`.
- The report may contain phone screenshots, masked/full account data, and phone numbers. Restrict access and apply a retention policy.
- The builder copies only `.jpg/.jpeg/.png/.webp/.xml/.json/.txt/.log` evidence; it does not read `.env`.

## 6. Visual style

For visual changes to the report, consult the `refactoring-ui` skill:

- use a constrained spacing/type scale, not ad-hoc values
- build hierarchy with weight and color before increasing size
- keep the dark token palette, tabular numbers, and restrained borders
- use shadows/depth sparingly; do not add external fonts, CDNs, or scripts

The current report already follows this direction. Keep it static and self-contained when iterating.

## 7. Boundaries

- No pixel-by-pixel baseline diff. This is evidence + semantic/status reporting.
- No phone action and no AI oracle call; those belong to `lamda-ui-automation`.
- One input run per report. Generate reports per run, or add an index later.
- Raw `report.html` from pytest-html is not re-skinned here; this report is its own static page.

## Resources

- `scripts/build_report.py` — standard-library-only report builder.
