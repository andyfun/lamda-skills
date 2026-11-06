---
name: lamda-phone-env
description: Bootstrap a fresh computer to connect to an Android phone running LAMDA/FIRERPA at `LAMDA_HOST:65000` (default `127.0.0.1`). Use when setting up a new machine, installing Python/Node dependencies, checking TCP or LAMDA connectivity, taking the first screenshot/XML, or troubleshooting "nc works but Python cannot connect" before any UI automation.
---

# LAMDA Phone Environment

Default target: **`127.0.0.1:65000`**, which works when `adb forward tcp:65000 tcp:65000` is active. For a phone reached over the LAN, pass `--host <phone-ip>` or export `LAMDA_HOST`; never assume a stale address.

This skill is the environment layer. For UI flows and screenshot regression, use the `lamda-ui-automation` skill after this check passes.

## 0. Phone preconditions

- LAMDA/FIRERPA service is running on the phone.
- Phone and computer are on the same LAN/VPN; AP isolation is off.
- Phone screen is unlocked and awake; battery optimization is disabled.
- The target app is installed if the task is app-specific.

Quick reachability check from the new computer:

```bash
nc -vz 127.0.0.1 65000
# or: python3 -c "import socket; socket.create_connection(('127.0.0.1',65000),3); print('TCP OK')"
```

## 0.1 Install FIRERPA / Shizuku if missing

If the phone does not have `com.firerpa` or `moe.shizuku.privileged.api`,
bootstrap it over a **USB adb** connection first. LAMDA cannot install itself
before its service exists.

```bash
adb devices                     # must show "device", not "unauthorized"
scripts/device_bootstrap.sh --serial <adb-serial> \
  --kit ~/workspace/lamda-kit \
  --host <phone-ip>
```

The script:

1. checks FIRERPA / Shizuku / ABI / Android version
2. installs `firerpa.apk` + `shizuku.apk` (APK mode) when missing
3. starts Shizuku through adb
4. opens FIRERPA and waits for `65000` when `--host` is supplied

After the script, finish these **once** in the FIRERPA app:

1. allow Shizuku; `IDENTITY` should show `shell (shizuku)` or `root`
2. tap **Download now** to install the server, then **Start Service**
3. keep **Auto start on boot** enabled if needed

`--kit` defaults to `$LAMDA_KIT` or `~/workspace/lamda-kit`; it must contain
`files/firerpa.apk`, `files/shizuku.apk`, `install.sh`, and `shizuku-start.sh`.
The script does not download the 214MB server package; the app does that.

For a **rooted** device, APK mode still works (the app can use root). The
kit's `install.sh --mode manual` path is optional; it installs under
`/data/server` and needs a manual start after reboot.

If the phone has no USB adb and LAMDA is also absent, the phone must be
provisioned manually or through an existing device-management channel; do not
assume LAMDA can bootstrap itself.

## 1. Install Python and the LAMDA client

Use Python 3.11–3.13.

### Linux

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### macOS / Windows

Install Python 3.11+ from python.org or Homebrew. On Windows, enable **Add Python to PATH**.

Create an isolated workspace:

```bash
mkdir -p ~/lamda-workspace
cd ~/lamda-workspace
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install "lamda==10.9"
```

Keep the client pinned to the server version. If the server is not 10.9, match it explicitly.

### Interpreter rule

Do **not** rely on `source .venv/bin/activate` persisting across separate agent shell calls. Prefer the absolute interpreter path:

```bash
export LAMDA_PYTHON="$HOME/lamda-workspace/.venv/bin/python"
"$LAMDA_PYTHON" -c "import lamda, sys; print('lamda ok', sys.executable)"
```

If `python3 -c "import lamda"` raises `ModuleNotFoundError`, that is an interpreter/installation problem, **not** a phone or network problem. Use the venv Python above; if the venv does not exist, run the creation/install steps first.

## 2. Run the environment check

From this skill directory, use the venv Python explicitly:

```bash
export LAMDA_PYTHON="${LAMDA_PYTHON:-$HOME/lamda-workspace/.venv/bin/python}"

"$LAMDA_PYTHON" scripts/lamda_env_check.py \
  --host 127.0.0.1 \
  --out captures
```

Or use environment variables:

```bash
export LAMDA_HOST=127.0.0.1
export LAMDA_PORT=65000
export LAMDA_PYTHON="${LAMDA_PYTHON:-$HOME/lamda-workspace/.venv/bin/python}"
"$LAMDA_PYTHON" scripts/lamda_env_check.py --out captures
```

If the venv is somewhere else, point `LAMDA_PYTHON` at that interpreter.

Expected output includes:

```text
tcp   : OK
server: 10.9 (arm64-v8a)
app   : ...
screen: on=True locked=False
shot  : ... bytes
xml   : ... bytes
OK
```

`captures/` contains `screen.jpg`, `window.xml`, and `meta.json`.

Options:

- `--allow-locked` captures a locked screen instead of failing.
- `--certificate /path/to/lamda.pem` when the server uses TLS.
- `--port` when the server is not on `65000`.

## 3. Optional Node toolchain

Only install Node when the task needs Midscene visual assertions. Screenshot/XML via LAMDA does **not** need Node.

```bash
node --version        # requires Node 20+
npm install @midscene/core@1.13.3
```

Do not add Node/model setup to a simple connectivity or screenshot task.

## 4. Failure handling

| Symptom | Action |
|---|---|
| `nc` fails | Check phone IP, same LAN/VPN, AP isolation, firewall, LAMDA service |
| `nc` works, Python fails | Check port/certificate; use the phone LAN IP, not `127.0.0.1` |
| `StatusCode.UNAVAILABLE` | LAMDA not running, wrong port, or network blocked |
| TLS/certificate error | Pass `--certificate /path/to/lamda.pem` |
| Screen locked | Unlock manually; `wake_up()` does not bypass a secure lock |
| Black/very small screenshot | Screen off, locked, or secure surface; wake/unlock and retry |
| macOS `EHOSTUNREACH` | Local Network permission; use a system Python/proxy or fix permissions |
| `ModuleNotFoundError: No module named 'lamda'` | Wrong interpreter or venv missing; use `$HOME/lamda-workspace/.venv/bin/python` and install `lamda==10.9` |
| `pip install lamda` build error | Use Python 3.11/3.12; install build tools if no wheel exists |

Do not put `LAMDA_PROXY=127.0.0.1:7000` on a Linux/Docker host. That address points at the host itself. Use the phone LAN IP; use `host.docker.internal:7000` only for Docker Desktop with a host-side proxy.

## 5. Security

LAMDA’s default `65000` has no authentication. Anyone who can reach it can control the phone, including the WebUI shell. Keep it on a trusted LAN/VPN, restrict source IPs, and never expose `65000` to the public internet.

## Resources

- `scripts/lamda_env_check.py` — standalone TCP + LAMDA + screenshot/XML check.
- `scripts/device_bootstrap.sh` — check/install FIRERPA + Shizuku over USB adb.
- `references/troubleshooting.md` — extended connection checklist.
