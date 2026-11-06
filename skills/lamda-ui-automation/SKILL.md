---
name: lamda-ui-automation
description: Write and run LAMDA Android UI automation and screenshot regression against a phone at `LAMDA_HOST:65000` (default `127.0.0.1`). Use when the user wants to automate an app flow, inspect UI state, capture screenshot/XML evidence, assert selectors/text, or add a read-only visual oracle; do not use for machine setup or connectivity-only questions.
---

# LAMDA UI Automation

Default target: **`127.0.0.1:65000`** (works with `adb forward tcp:65000 tcp:65000`). For a phone on the LAN, use `--host <phone-ip>` or `LAMDA_HOST`. Verify the address before starting.

Run the environment check first (`lamda-phone-env` or a direct `Device` probe). If the screen is off, wake it; if it is locked, stop and ask the user to unlock it. Do not write a flow against a black or locked screen.

If the phone does **not** have FIRERPA/Shizuku installed, run
`lamda-phone-env/scripts/device_bootstrap.sh` over USB adb first; LAMDA cannot
bootstrap itself before its service exists. Then return to this skill.

When the user asks for a screenshot or flow, **execute it**, do not merely print the command. Use an interpreter that can import `lamda`; if `python3 -c "import lamda"` fails, use `$HOME/lamda-workspace/.venv/bin/python`, a project `.venv/bin/python`, or install `lamda==10.9` before running the script. `ModuleNotFoundError` is an interpreter problem, not a phone/network failure.

## 1. Workflow

1. Connect and verify `server_info()`, current app, screen-on/locked state.
2. If app-specific, check `app.is_installed()` and start it; confirm foreground.
3. Dump XML **before** choosing selectors.
4. Prefer stable selectors: `resourceId` first, then `text`/`description`; use regex/contains only when the value is dynamic.
5. Act with selector methods; wait for an explicit postcondition, not a fixed sleep.
6. Re-dump and verify the resulting state. Save screenshot + XML for key states and failures.
7. Add a read-only visual oracle only after deterministic checks; never let the model click, type, or navigate.

## 2. Minimal capture / smoke check

From this skill directory:

```bash
# Use the Python that has lamda installed.
export LAMDA_PYTHON="$HOME/lamda-workspace/.venv/bin/python"
"$LAMDA_PYTHON" -c "import lamda, sys; print('lamda ok', sys.executable)"

"$LAMDA_PYTHON" scripts/lamda_capture.py \
  --host 127.0.0.1 \
  --app com.example.androidtest \
  --out captures
```

It checks the app, wakes the screen, starts the app, verifies foreground, and writes `screen.jpg`, `window.xml`, `meta.json`.

Use it to prove the device/app/evidence path before writing a longer flow.

### 2.1 AI smoke for Unity/opaque apps

Use `scripts/ai_smoke.py` when the app renders into one Surface and XML cannot
assert the visible state (Unity, games, Flutter canvases). The runner is
app-agnostic; it provides only primitives:

```text
wait / capture / tap / probe / assert
```

The flow comes from a JSON config — no app names, prompts, taps or expected
states are hardcoded in the script.

```bash
# Run from the sdk-autotest repo so oracle/oracle.mjs and .env resolve.
"$LAMDA_PYTHON" ~/.config/opencode/skills/lamda-ui-automation/scripts/ai_smoke.py \
  --host <phone-ip> \
  --app <package> \
  --activity <package>/<activity> \
  --config references/ai-smoke.example.json \
  --out artifacts/<run>
```

Minimal config:

```json
{
  "steps": [
    {"type": "wait", "seconds": 15},
    {"type": "capture", "name": "step_01.jpg"},
    {"type": "probe", "name": "loading", "prompt": "...",
     "if_true": [{"type": "wait", "seconds": 10}]},
    {"type": "tap", "x": 0, "y": 0},
    {"type": "assert", "name": "final", "prompt": "..."}
  ]
}
```

- `probe` is a read-only boolean oracle; `if_true`/`if_false` contain nested steps.
- `assert` is a read-only semantic assertion; a failure marks the run failed.
- `tap` uses deterministic coordinates from the config; the model never acts.
- The runner reads `.env` for `MIDSCENE_MODEL_*`; screenshots are sized from the
  actual JPEG, so no hardcoded resolution is required.
- `--no-root-setup` and `--no-cold-start` support capture-only/read-only runs.
- Generated `summary.json` is directly consumable by the `lamda-report` skill.

Copy `references/ai-smoke.example.json` as a starting point. It intentionally
contains no app-specific prompts or coordinates.

## 3. Selector-driven flow

```python
from pathlib import Path
from lamda.client import Device

d = Device("127.0.0.1", 65000)
app = d.application("com.example.androidtest")
assert app.is_installed()
app.start()
assert app.is_foreground()

# Derive these selectors from a real XML dump; placeholders only.
entry = d(resourceId="com.example.androidtest:id/btn_login")
assert entry.wait_for_exists(5000), "login entry did not appear"
entry.click()

phone = d(className="android.widget.EditText")
assert phone.wait_for_exists(5000), "phone input did not appear"
phone.click()
phone.set_text("13800000000")

next_step = d(text="下一步")
assert next_step.wait_for_exists(5000), "next button did not appear"
next_step.click()

assert d(textContains="验证码").wait_for_exists(5000), "code page did not appear"
```

Rules:

- A selector match is not automatically the right element. Constrain by package/resource-id and verify.
- Re-locate elements after navigation, scroll, refresh, or dialog changes; do not reuse stale element objects.
- `wait_for_exists(timeout)` and `wait_until_gone(timeout)` use milliseconds.
- `exists()` is a snapshot, not readiness. Wait for the postcondition you actually need.
- For text input, click the field, then `set_text()`; verify the text or the resulting screen.
- Use `execute_script()` for phone shell commands; there is no `d.shell()`.

## 4. Evidence and failure handling

```python
from pathlib import Path

case = Path("artifacts") / "case_name"
case.mkdir(parents=True, exist_ok=True)

d.screenshot(90).save(case / "step_01.jpg")
case.joinpath("step_01.xml").write_bytes(
    d.dump_window_hierarchy().getvalue()
)
```

On failure, write `failure.jpg`, `failure.xml`, and the exception text. Evidence must never hide the original failure.

Minimum success checks:

- Screenshot is non-empty and not obviously black/locked.
- XML contains `<hierarchy>`.
- The expected app is foreground at the boundary.
- The specific selector/text/state assertion passes.

Do not treat “no exception” as success.

## 5. Read-only visual oracle

Use a visual oracle for semantic checks that XML cannot express, not for actions.

- Input: one screenshot plus prompt.
- Output: boolean / value; no `aiTap`, `aiInput`, `aiAct`.
- Interface: `actionSpace: []`, `domIncluded: false`.
- Record prompt, pass/reject, thought, model usage.
- Put deterministic XML assertions first; if they fail, do not spend an AI call.

See `references/visual_oracle.md` for a minimal `@midscene/core` script.

## 6. Report

After a capture or test run, hand the evidence directory to the `lamda-report` skill. It produces a static dark report with embedded screenshots, XML/JSON evidence, timings, and oracle results; it does not need the phone or a model call.

## 7. Safety

- One phone, one action owner, one run at a time. Use a lock/queue for CI.
- Do not use coordinate clicks when a selector is available.
- Do not submit real payments or destructive account actions without explicit user confirmation.
- Do not test from a locked screen or a secure/black surface.
- LAMDA’s port has no authentication; keep it on a trusted LAN/VPN.

## Resources

- `scripts/lamda_capture.py` — app check/start + screenshot/XML capture.
- `scripts/ai_smoke.py` — root setup + cold start + read-only visual probes +
  evidence/summary for opaque/Unity apps.
- `references/ai-smoke.example.json` — app-agnostic step-config template.
- `references/lamda_api.md` — `lamda==10.9` selector/action/evidence cheat sheet.
- `references/visual_oracle.md` — optional read-only Midscene assertion.
