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
| `refactoring-ui` | Design rules from *Refactoring UI*: spacing/type/color scales, hierarchy, depth | no |

## Install

```bash
# global (available in every project)
npx skills add <owner>/lamda-skills -a opencode -g

# project-local (committed with the repo)
npx skills add <owner>/lamda-skills -a opencode

# one skill only
npx skills add <owner>/lamda-skills --skill lamda-report -a opencode -g

# from a local checkout
npx skills add . -a opencode --copy
```

OpenCode resolves skills from `~/.config/opencode/skills/` (global) and
`.agents/skills/` / `.opencode/skills/` (project).

## Configuration

Nothing is hard-coded. Set these when the defaults do not fit:

| Variable | Default | Meaning |
|---|---|---|
| `LAMDA_HOST` | `127.0.0.1` | Phone address. `127.0.0.1` works with `adb forward tcp:65000 tcp:65000`; use the LAN IP otherwise |
| `LAMDA_PORT` | `65000` | LAMDA gRPC/HTTP port |
| `LAMDA_PYTHON` | current interpreter | Interpreter that has `lamda` installed (a venv activate does not survive between commands) |

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
