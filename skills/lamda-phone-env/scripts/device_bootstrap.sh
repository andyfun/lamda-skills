#!/usr/bin/env bash
# Check / install FIRERPA + Shizuku on a USB-connected Android phone.
#
# Requires: adb in PATH, an authorized device, and a lamda-kit checkout
# containing files/firerpa.apk, files/shizuku.apk and install.sh.
#
# Usage:
#   ./device_bootstrap.sh --serial <adb-serial>
#   ./device_bootstrap.sh --serial <adb-serial> --mode check
#   ./device_bootstrap.sh --serial <adb-serial> --kit ~/workspace/lamda-kit
#   ./device_bootstrap.sh --serial <adb-serial> --host 192.168.1.50
#
# APK mode is the recommended non-root path. It installs the manager apps and
# starts Shizuku via adb; the remaining server download/start is done in the
# FIRERPA app (the script prints the exact steps).
set -euo pipefail

KIT="${LAMDA_KIT:-$HOME/workspace/lamda-kit}"
SERIAL=""
HOST=""
PORT=65000
MODE="apk"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial|-s) SERIAL="${2:-}"; shift 2 ;;
    --kit) KIT="${2:-}"; shift 2 ;;
    --host) HOST="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

ADB=(adb)
[[ -n "$SERIAL" ]] && ADB+=(-s "$SERIAL")
FIRERPA=com.firerpa
SHIZUKU=moe.shizuku.privileged.api

command -v adb >/dev/null || {
  echo "adb not found; install Android platform-tools first" >&2
  exit 2
}

if ! "${ADB[@]}" get-state >/dev/null 2>&1; then
  echo "no authorized adb device${SERIAL:+ ($SERIAL)}; run: adb devices" >&2
  exit 2
fi

has_pkg() {
  "${ADB[@]}" shell pm list packages 2>/dev/null | tr -d '\r' | grep -qx "package:$1"
}

echo "device : $("${ADB[@]}" shell getprop ro.product.model | tr -d '\r')"
echo "android: $("${ADB[@]}" shell getprop ro.build.version.release | tr -d '\r')"
echo "abi    : $("${ADB[@]}" shell getprop ro.product.cpu.abi | tr -d '\r')"
echo "firerpa: $(has_pkg "$FIRERPA" && echo installed || echo missing)"
echo "shizuku: $(has_pkg "$SHIZUKU" && echo installed || echo missing)"

if [[ "$MODE" == "check" ]]; then
  if [[ -n "$HOST" ]]; then
    if nc -z -G 2 "$HOST" "$PORT" 2>/dev/null; then
      echo "service: http://$HOST:$PORT is reachable"
    else
      echo "service: not reachable at $HOST:$PORT" >&2
      exit 1
    fi
  fi
  exit 0
fi

if [[ ! -d "$KIT" ]]; then
  echo "lamda-kit not found: $KIT" >&2
  echo "set LAMDA_KIT or pass --kit /path/to/lamda-kit" >&2
  exit 2
fi

need_install=0
has_pkg "$FIRERPA" || need_install=1
has_pkg "$SHIZUKU" || need_install=1

if [[ "$need_install" == 1 ]]; then
  if [[ "$MODE" == "apk" ]]; then
    [[ -f "$KIT/files/firerpa.apk" && -f "$KIT/files/shizuku.apk" ]] || {
      echo "missing $KIT/files/firerpa.apk or shizuku.apk" >&2
      exit 2
    }
    echo "installing FIRERPA + Shizuku (APK mode)..."
    "${ADB[@]}" install -r -g "$KIT/files/shizuku.apk" >/dev/null
    "${ADB[@]}" install -r -g "$KIT/files/firerpa.apk" >/dev/null
  elif [[ "$MODE" == "manual" ]]; then
    echo "running lamda-kit manual install..."
    (cd "$KIT" && ./install.sh --mode manual ${SERIAL:+-s "$SERIAL"}) || true
  else
    echo "unknown --mode: $MODE (use apk|manual|check)" >&2
    exit 2
  fi
fi

if has_pkg "$SHIZUKU"; then
  echo "starting Shizuku via adb..."
  "$KIT/shizuku-start.sh" ${SERIAL:+"$SERIAL"} || true
fi

if has_pkg "$FIRERPA"; then
  "${ADB[@]}" shell am start -n com.firerpa/.MainActivity >/dev/null 2>&1 || true
fi

cat <<'TIP'

Next steps (APK mode, once per install):
  1. In FIRERPA, allow Shizuku when prompted.
     IDENTITY should become "shell (shizuku)" or "root".
  2. Tap "Download now" to install the server, then "Start Service".
  3. Keep "Auto start on boot" enabled if you want it to survive reboot.

Verify from the computer:
  nc -vz <phone-ip> 65000
  # or, from lamda-phone-env:
  python scripts/lamda_env_check.py --host <phone-ip>
TIP

if [[ -n "$HOST" ]]; then
  for _ in $(seq 1 30); do
    if nc -z -G 2 "$HOST" "$PORT" 2>/dev/null; then
      echo "service ready: http://$HOST:$PORT"
      exit 0
    fi
    sleep 2
  done
  echo "service not ready at $HOST:$PORT; finish the in-app steps above" >&2
  exit 1
fi
