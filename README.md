# LAMDA Skills

Agent skills for Android UI automation, evidence reporting, and phone environment setup.
Compatible with OpenCode, Claude Code, Cursor, Codex and any agent that follows the
[Agent Skills](https://agentskills.io) layout.

## Skills

| Skill | What it does | Needs a phone |
|---|---|---|
| `lamda-phone-env` | Bootstrap a machine to talk to a LAMDA/FIRERPA phone: TCP check, Python/Node deps, first screenshot/XML | yes |
| `lamda-ui-automation` | Write and run UI flows, capture screenshot/XML evidence, deterministic selector assertions, read-only visual oracle | yes |
| `lamda-report` | Turn a run directory into a dark, self-contained HTML report with per-case pages and evidence | no |
| `runtime-protocol-report` | Turn captured HTTP/TLS traffic into an API contract matrix + standalone HTML report | no |
| `refactoring-ui` | Design rules from *Refactoring UI*: spacing/type/color scales, hierarchy, depth | no |

## Install

Two ways: the [`skills`](https://github.com/vercel-labs/skills) CLI (recommended), or the
packaged `.skill` zips.

### OpenCode

```bash
npx skills add andyfun/lamda-skills -a opencode -g     # global
npx skills add andyfun/lamda-skills -a opencode        # project
```

### Cursor

```bash
npx skills add andyfun/lamda-skills -a cursor -g       # global  → ~/.cursor/skills/
npx skills add andyfun/lamda-skills -a cursor          # project → .cursor/skills/
```

Cursor also reads `.agents/skills/` and `~/.agents/skills/`, plus the Claude and Codex
directories. So one install can serve both agents:

```bash
npx skills add andyfun/lamda-skills -a opencode -a cursor -g   # → ~/.agents/skills/
```

After that, Cursor lists them under **Customize → Skills** and you can invoke one with
`/skill-name` in Agent chat. Restart the window if the list looks stale.

Cursor cannot install straight from a bare repository — that path needs a plugin
marketplace — but a normal folder install works exactly like above.

### Offline / `.skill` packages

Every skill also ships as a zip with `<name>/SKILL.md` at the root:

```bash
unzip -o lamda-report.skill -d ~/.config/opencode/skills/   # OpenCode
unzip -o lamda-report.skill -d ~/.cursor/skills/            # Cursor
unzip -o lamda-report.skill -d ~/.agents/skills/            # both agents
```

### Where skills are discovered

| Agent | Global | Project |
|---|---|---|
| OpenCode | `~/.config/opencode/skills/` | `.opencode/skills/`, `.agents/skills/` |
| Cursor | `~/.cursor/skills/` | `.cursor/skills/`, `.agents/skills/` |
| **Both (shared)** | `~/.agents/skills/` | `.agents/skills/` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | `.codex/skills/` |

Keep the folder name identical to the `name:` field in `SKILL.md`; both agents reject
mismatches.

## Configuration

Nothing is hard-coded. Set these when the defaults do not fit:

| Variable | Default | Meaning |
|---|---|---|
| `LAMDA_HOST` | `127.0.0.1` | Phone address. `127.0.0.1` works with `adb forward tcp:65000 tcp:65000`; use the LAN IP otherwise |
| `LAMDA_PORT` | `65000` | LAMDA gRPC/HTTP port |
| `LAMDA_PYTHON` | current interpreter | Interpreter that has `lamda` installed (a venv activate does not survive between commands) |
| `LAMDA_APK_BASE_URL` | unset | Mirror root for `firerpa.apk` / `shizuku.apk` when GitHub is unreachable |
| `LAMDA_APK_URL` / `LAMDA_FIRERPA_APK_URL` | unset | Direct APK URL override used by `device_bootstrap.sh --download` |

```bash
npx skills add ...
export LAMDA_HOST=192.168.1.50
export LAMDA_PYTHON=$HOME/.venvs/lamda/bin/python
```

## Requirements

- Python 3.9+ with `lamda` for the two phone skills
- `adb` for device-side helpers
- Node 22.20+ only if you use the `npx skills` CLI itself
- No API keys, no credentials, no telemetry

## Safety notes

- Skills run with the agent's full permissions. Read `SKILL.md` before installing from
  anywhere, including this repo.
- The automation skills treat Midscene as read-only (`actionSpace: []`, `domIncluded: false`);
  only LAMDA changes device state.
- Reports can embed screenshots, XML and logs from a real device. Treat generated
  `artifacts/` as potentially identifying and keep them out of version control.

## Third-party

`refactoring-ui` is MIT licensed, © 2026 s13k. Its `LICENSE` is kept inside the skill
directory. Everything else is MIT, see [LICENSE](LICENSE).
