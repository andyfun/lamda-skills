#!/usr/bin/env bash
# Check / install FIRERPA + Shizuku on a USB-connected Android phone.
#
# APKs are resolved from the first location that has them:
#   1. --apk-dir DIR
#   2. --kit DIR/files            (a lamda-kit checkout)
#   3. ~/.cache/lamda-kit/files   (populated by --download)
#   4. --download                 (fetch, then install from the cache)
#
# Usage:
#   ./device_bootstrap.sh --serial <adb-serial> --apk-dir ~/apks
#   ./device_bootstrap.sh --serial <adb-serial> --kit ~/workspace/lamda-kit
#   ./device_bootstrap.sh --serial <adb-serial> --download
#   ./device_bootstrap.sh --serial <adb-serial> --mode check --host 192.168.1.50
#   ./device_bootstrap.sh --dry-run --apk-dir ~/apks
#
# APK mode is the recommended non-root path. It installs the manager apps and
# starts Shizuku via adb; the remaining server download/start is done in the
# FIRERPA app (the script prints the exact steps).
#
# Download sources (override with env vars):
#   LAMDA_FIRERPA_APK_URL   direct URL for firerpa.apk
#   LAMDA_SHIZUKU_APK_URL   direct URL for shizuku.apk
#   LAMDA_APK_BASE_URL      mirror root, expects <base>/firerpa.apk and <base>/shizuku.apk
#   LAMDA_CACHE             cache dir (default ~/.cache/lamda-kit)
set -euo pipefail

KIT="${LAMDA_KIT:-}"
APK_DIR=""
CACHE="${LAMDA_CACHE:-$HOME/.cache/lamda-kit}"
SERIAL=""
HOST=""
PORT=65000
MODE="apk"
DOWNLOAD=0
DRY_RUN=0

# Official sources. Shizuku publishes APKs on GitHub Releases; FIRERPA (lamda)
# publishes only server tarballs, so its APK has no official direct link.
SHIZUKU_APK_URL="${LAMDA_SHIZUKU_APK_URL:-https://github.com/RikkaApps/Shizuku/releases/download/v13.6.0/shizuku-v13.6.0.r1086.2650830c-release.apk}"
FIRERPA_APK_URL="${LAMDA_FIRERPA_APK_URL:-}"
SHIZUKU_APK_SHA256="${LAMDA_SHIZUKU_APK_SHA256:-}"
FIRERPA_APK_SHA256="${LAMDA_FIRERPA_APK_SHA256:-}"

if [[ -n "${LAMDA_APK_BASE_URL:-}" ]]; then
  [[ -n "$FIRERPA_APK_URL" ]] || FIRERPA_APK_URL="${LAMDA_APK_BASE_URL%/}/firerpa.apk"
  [[ -n "$SHIZUKU_APK_URL" ]] || SHIZUKU_APK_URL="${LAMDA_APK_BASE_URL%/}/shizuku.apk"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serial|-s) SERIAL="${2:-}"; shift 2 ;;
    --kit) KIT="${2:-}"; shift 2 ;;
    --apk-dir) APK_DIR="${2:-}"; shift 2 ;;
    --host) HOST="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --download) DOWNLOAD=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

FIRERPA=com.firerpa
SHIZUKU=moe.shizuku.privileged.api
CACHE_DIR="$CACHE/files"

find_apk() {
  local name="$1" d
  for d in "$APK_DIR" "${KIT:+$KIT/files}" "$CACHE_DIR"; do
    [[ -n "$d" && -f "$d/$name" ]] && { printf '%s\n' "$d/$name"; return 0; }
  done
  return 1
}

url_for() {
  case "$1" in
    firerpa.apk) printf '%s\n' "$FIRERPA_APK_URL" ;;
    shizuku.apk) printf '%s\n' "$SHIZUKU_APK_URL" ;;
  esac
}

download_apk() {
  local name="$1" url="$2" dest="$3" expected_sha="${4:-}"
  if [[ -z "$url" ]]; then
    echo "  $name : no download URL configured" >&2
    case "$name" in
      firerpa.apk)
        echo "           FIRERPA ships no APK on GitHub releases." >&2
        echo "           upload it once, then set LAMDA_FIRERPA_APK_URL or LAMDA_APK_BASE_URL" >&2 ;;
      shizuku.apk)
        echo "           see https://github.com/RikkaApps/Shizuku/releases" >&2 ;;
    esac
    return 1
  fi
  if ! command -v curl >/dev/null; then
    echo "  $name : curl not found, cannot download" >&2
    return 1
  fi
  echo "  $name : downloading from $url"
  mkdir -p "$(dirname "$dest")"
  if ! curl -fL --retry 2 --connect-timeout 10 --max-time 900 -o "$dest.part" "$url"; then
    rm -f "$dest.part"
    echo "  $name : download failed (404, blocked network, or mirror unreachable)" >&2
    return 1
  fi

  # A mirror may answer 200 with an HTML login page; an APK is a zip and starts with "PK".
  if [[ "$(head -c 2 "$dest.part" 2>/dev/null)" != "PK" ]]; then
    echo "  $name : not an APK (missing PK header) — wrong URL or a proxy/login page" >&2
    rm -f "$dest.part"
    return 1
  fi

  if [[ -n "$expected_sha" ]]; then
    local actual
    actual="$(shasum -a 256 "$dest.part" | awk '{print $1}')"
    if [[ "$actual" != "$expected_sha" ]]; then
      echo "  $name : sha256 mismatch" >&2
      echo "           expected $expected_sha" >&2
      echo "           actual   $actual" >&2
      rm -f "$dest.part"
      return 1
    fi
  fi

  mv "$dest.part" "$dest"
  echo "  $name : saved to $dest ($(du -h "$dest" | cut -f1))"
}

ensure_apk() {
  local name="$1" found expected=""
  if found="$(find_apk "$name")"; then
    printf '%s\n' "$found"
    return 0
  fi
  case "$name" in
    firerpa.apk) expected="$FIRERPA_APK_SHA256" ;;
    shizuku.apk) expected="$SHIZUKU_APK_SHA256" ;;
  esac
  if [[ "$DOWNLOAD" == 1 ]]; then
    download_apk "$name" "$(url_for "$name")" "$CACHE_DIR/$name" "$expected" >&2 || return 1
    printf '%s\n' "$CACHE_DIR/$name"
    return 0
  fi
  return 1
}

if [[ "$DRY_RUN" == 1 ]]; then
  echo "mode    : $MODE"
  echo "cache   : $CACHE_DIR"
  [[ -n "$KIT" ]] && echo "kit     : $KIT"
  [[ -n "$APK_DIR" ]] && echo "apk-dir : $APK_DIR"
  for name in shizuku.apk firerpa.apk; do
    if found="$(find_apk "$name")"; then
      echo "$name : $found"
    elif [[ "$DOWNLOAD" == 1 ]]; then
      echo "$name : missing, would download from $(url_for "$name" | sed 's/^$/<no url configured>/')"
    else
      echo "$name : missing (pass --apk-dir, --kit, or --download)"
    fi
  done
  exit 0
fi

ADB=(adb)
[[ -n "$SERIAL" ]] && ADB+=(-s "$SERIAL")

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

need_install=0
has_pkg "$FIRERPA" || need_install=1
has_pkg "$SHIZUKU" || need_install=1

if [[ "$need_install" == 1 ]]; then
  if [[ "$MODE" == "apk" ]]; then
    FIRERPA_APK=""
    SHIZUKU_APK=""
    if has_pkg "$FIRERPA" 2>/dev/null; then :; else
      FIRERPA_APK="$(ensure_apk firerpa.apk)" || {
        echo "cannot locate firerpa.apk" >&2
        echo "  tried: ${APK_DIR:-<no --apk-dir>}, ${KIT:-<no --kit>}/files, $CACHE_DIR" >&2
        echo "  FIRERPA publishes no APK asset on GitHub; point --apk-dir or LAMDA_FIRERPA_APK_URL at a copy" >&2
        exit 2
      }
    fi
    if has_pkg "$SHIZUKU" 2>/dev/null; then :; else
      SHIZUKU_APK="$(ensure_apk shizuku.apk)" || {
        echo "cannot locate shizuku.apk" >&2
        echo "  tried: ${APK_DIR:-<no --apk-dir>}, ${KIT:-<no --kit>}/files, $CACHE_DIR" >&2
        echo "  official: https://github.com/RikkaApps/Shizuku/releases" >&2
        exit 2
      }
    fi
    echo "installing (apk mode)..."
    [[ -n "$SHIZUKU_APK" ]] && { echo "  shizuku <- $SHIZUKU_APK"; "${ADB[@]}" install -r -g "$SHIZUKU_APK" >/dev/null; }
    [[ -n "$FIRERPA_APK" ]] && { echo "  firerpa <- $FIRERPA_APK"; "${ADB[@]}" install -r -g "$FIRERPA_APK" >/dev/null; }
  elif [[ "$MODE" == "manual" ]]; then
    if [[ -z "$KIT" || ! -x "$KIT/install.sh" ]]; then
      echo "--mode manual needs a lamda-kit checkout with install.sh (--kit DIR)" >&2
      exit 2
    fi
    echo "running lamda-kit manual install..."
    (cd "$KIT" && ./install.sh --mode manual ${SERIAL:+-s "$SERIAL"}) || true
  else
    echo "unknown --mode: $MODE (use apk|manual|check)" >&2
    exit 2
  fi
fi

if has_pkg "$SHIZUKU"; then
  if [[ -n "$KIT" && -x "$KIT/shizuku-start.sh" ]]; then
    echo "starting Shizuku via adb..."
    "$KIT/shizuku-start.sh" ${SERIAL:+"$SERIAL"} || true
  else
    echo "Shizuku installed; no shizuku-start.sh available."
    echo "  open Shizuku and start it (Wireless debugging or root), then return."
  fi
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
