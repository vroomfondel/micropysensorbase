#!/bin/bash
#
# Host-side driver for migrate_flat_to_package.py.
#
# Deploys the migration script to one device, quiesces the running old install,
# triggers the migration and verifies the result against the mqtt broker.
#
#   ./migrate_flat_to_package.sh --ip <device-ip>
#   ./migrate_flat_to_package.sh --port /dev/ttyUSB0
#   ./migrate_flat_to_package.sh --ip <device-ip> --check-only
#
# Serial is the safer transport: the raw repl transfers the input as a block, so
# the device's own log output cannot corrupt it. Over WebREPL a firing
# measure-callback logs into the same session and mangles pasted lines.

set -euo pipefail
cd "$(dirname "$0")"

CONFIG="esp32config.local.json"
SCRIPT="migrate_flat_to_package.py"
WEBREPLCMD=".venv/bin/webreplcmd"

# kills the periodic callbacks of the old install. Has to run in the *same*
# session as the command it precedes: a callback goes measure -> publish ->
# ensure_wifi_catch_reset(), which resets the device mid-migration.
QUIESCE='from machine import Timer; [Timer(i).deinit() for i in range(4)]'

IP=""
PORT=""
MAC=""
ASSUME_YES=false
CHECK_ONLY=false
SKIP_CONFIG=false

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "=== $* ==="; }

usage() {
    sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'
    echo
    echo "Options:"
    echo "  --ip <addr>      migrate over WebREPL"
    echo "  --port <dev>     migrate over serial mpremote"
    echo "  --mac <hex>      MAC without colons; read from the device otherwise"
    echo "  --check-only     pre-flight only, change nothing"
    echo "  --skip-config    do not push esp32config.local.json to the device"
    echo "  --yes            do not ask for confirmation"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --ip) IP="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --mac) MAC="$2"; shift 2 ;;
        --check-only) CHECK_ONLY=true; shift ;;
        --skip-config) SKIP_CONFIG=true; shift ;;
        --yes|-y) ASSUME_YES=true; shift ;;
        -h|--help) usage ;;
        *) die "unknown option: $1" ;;
    esac
done

[ -n "$IP" ] || [ -n "$PORT" ] || die "pass either --ip or --port (--help)"
[ -z "$IP" ] || [ -z "$PORT" ] || die "--ip and --port are mutually exclusive"

# ---------------------------------------------------------------- transport

# read only, without touching the timers: quiescing would also kill the msgtimer
# and thereby silence the mqtt connection of a healthy device. Nothing may be
# changed for identification and --check-only.
dev_cmd_ro() {  # <python-one-liner>
    if [ -n "$PORT" ]; then
        mpremote connect "$PORT" exec "$1"
    else
        "$WEBREPLCMD" -i "$IP" -p "$WEBREPL_PW" cmd "$1"
    fi
}

dev_cmd() {  # <python-one-liner>, quiesces first
    if [ -n "$PORT" ]; then
        mpremote connect "$PORT" exec "$QUIESCE" >/dev/null 2>&1 || true
        mpremote connect "$PORT" exec "$1"
    else
        "$WEBREPLCMD" -i "$IP" -p "$WEBREPL_PW" -B "$QUIESCE" cmd "$1"
    fi
}

dev_put() {  # <local> <remote>
    if [ -n "$PORT" ]; then
        mpremote connect "$PORT" exec "$QUIESCE" >/dev/null 2>&1 || true
        mpremote connect "$PORT" fs cp "$1" ":$2"
    else
        "$WEBREPLCMD" -i "$IP" -p "$WEBREPL_PW" -B "$QUIESCE" put "$1" "$2"
    fi
}

mqtt_running_since() {  # <seconds>
    local w="${1:-6}"
    timeout $((w + 3)) mosquitto_sub -h "$MQ_HOST" -p "$MQ_PORT" -u "$MQ_USER" -P "$MQ_PASS" \
        -t "esp32/${CLIENTID}/status" -C 1 -W "$w" 2>/dev/null \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["value"]["running_since"])' 2>/dev/null || true
}

# ---------------------------------------------------------------- pre-flight

step "Pre-flight"

for t in jq python3 mosquitto_sub mosquitto_pub; do
    command -v "$t" >/dev/null || die "$t not found"
done
[ -f "$CONFIG" ] || die "$CONFIG missing"
[ -f "$SCRIPT" ] || die "$SCRIPT missing"

if [ -n "$PORT" ]; then
    command -v mpremote >/dev/null || die "mpremote not found"
    [ -c "$PORT" ] || die "$PORT does not exist"
    if command -v fuser >/dev/null && fuser "$PORT" >/dev/null 2>&1; then
        die "$PORT is busy - close the open session"
    fi
else
    [ -x "$WEBREPLCMD" ] || die "$WEBREPLCMD not found"
    # webreplcmd's -B/-c/-A paths call repl.send_cmd(), a method webrepl.py does
    # not have - it is sendcmd(). The exception is caught, printed and swallowed,
    # and the exit code stays 0. A broken -B would therefore skip the quiesce
    # unnoticed and let a measure callback reset the device mid-migration.
    if grep -q 'repl\.send_cmd(' "$WEBREPLCMD"; then
        die "$WEBREPLCMD calls repl.send_cmd(), which does not exist - the quiesce would be skipped silently.
       fix: sed -i 's/repl\.send_cmd(/repl.sendcmd(/g' $WEBREPLCMD"
    fi
    ping -c 2 -W 2 "$IP" >/dev/null 2>&1 || die "$IP does not answer to ping"
fi

MQ_HOST=$(jq -r '.mosquitto.MOSQUITTO_HOST' "$CONFIG")
MQ_PORT=$(jq -r '.mosquitto.MOSQUITTO_PORT' "$CONFIG")
MQ_USER=$(jq -r '.mosquitto.MOSQUITTO_USERNAME' "$CONFIG")
MQ_PASS=$(jq -r '.mosquitto.MOSQUITTO_PASSWORD' "$CONFIG")
WEBREPL_PW=$(jq -r '.webrepl.password' "$CONFIG")
MIP_INDEX=$(jq -r '.mip_index // empty' "$CONFIG")

[ -n "$MIP_INDEX" ] || die "no 'mip_index' in $CONFIG - the device reads it from there"
echo "  mip_index: $MIP_INDEX"

# The mipserver pulls from GitHub via git fetch. It does not see local or
# unpushed changes - the device would then silently get an older state.
if git rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain -- micropysensorbase/ 2>/dev/null)" ]; then
        echo "  WARNING: uncommitted changes under micropysensorbase/"
    fi
    git fetch -q origin 2>/dev/null || true
    ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
    [ "$ahead" = "0" ] || echo "  WARNING: $ahead commit(s) not pushed - mipserver serves the GitHub state"
fi

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MIP_INDEX/package/py/micropysensorbase/latest.json" || echo 000)
[ "$code" = "200" ] || die "mipserver answers with HTTP $code"
echo "  mipserver: HTTP 200"

step "Identify device"
if [ -z "$MAC" ]; then
    # Collect raw output first: with pipefail an empty grep would otherwise end
    # the script silently instead of showing the cause.
    raw=$(dev_cmd_ro 'import machine,ubinascii; print("MAC="+ubinascii.hexlify(machine.unique_id()).decode())' 2>&1 || true)
    MAC=$(printf '%s' "$raw" | grep -o 'MAC=[0-9a-f]*' | tail -1 | cut -d= -f2 || true)
    if [ -z "$MAC" ]; then
        echo "  device response:" >&2
        printf '%s\n' "$raw" | tail -3 | sed 's/^/    /' >&2
        if [ -z "$PORT" ]; then
            echo "  Note: WebREPL allows only ONE connection. An open or aborted" >&2
            echo "  session blocks the slot until the device restarts." >&2
        fi
        die "MAC could not be read - close the session or pass --mac"
    fi
fi
CLIENTID="esp32_${MAC}"
HOSTNAME=$(jq -r --arg m "$MAC" '.[$m].hostname // "?"' "$CONFIG")
echo "  MAC:      $MAC"
echo "  hostname: $HOSTNAME"
echo "  clientid: $CLIENTID"

BEFORE=$(mqtt_running_since 6)
echo "  running_since (before): ${BEFORE:-<none>}"

if $CHECK_ONLY; then
    step "check-only - nothing changed"
    exit 0
fi

# ---------------------------------------------------------------- confirmation

if ! $ASSUME_YES; then
    echo
    echo "Migrating $HOSTNAME ($CLIENTID) via ${IP:-$PORT}."
    echo "Deletes all files in / on the device and reinstalls via mip."
    read -r -p "Continue? [y/N] " answer
    case "$answer" in y|Y) ;; *) echo "aborted"; exit 1 ;; esac
fi

# ---------------------------------------------------------------- migration

if ! $SKIP_CONFIG; then
    step "esp32config.local.json to the device"
    dev_put "$CONFIG" "esp32config.local.json"
fi

step "$SCRIPT to the device"
dev_put "$SCRIPT" "$SCRIPT"

step "Trigger migration"
echo "On success the connection drops at the end (machine.reset) - that is expected."
echo
dev_cmd "import ${SCRIPT%.py}" || echo "(connection closed - see verification)"

# ---------------------------------------------------------------- verification

step "Verification via the broker"
echo "waiting for a new boot (max 120s)..."
deadline=$((SECONDS + 120))
AFTER=""
while [ $SECONDS -lt $deadline ]; do
    AFTER=$(mqtt_running_since 10)
    if [ -n "$AFTER" ] && [ "$AFTER" != "$BEFORE" ]; then
        break
    fi
done

if [ -n "$AFTER" ] && [ "$AFTER" != "$BEFORE" ]; then
    echo
    echo "OK: $HOSTNAME has rebooted."
    echo "    before: ${BEFORE:-<none>}"
    echo "    after:  $AFTER"
    echo
    echo "Check the measurements (if nothing arrives, setup_pins hit an error):"
    echo "  mosquitto_sub -h $MQ_HOST -p $MQ_PORT -u $MQ_USER -P '<pw>' \\"
    echo "    -t 'esp32/${CLIENTID}/ma' -t 'esp32/${CLIENTID}/logging' -v -W 90"
else
    echo
    echo "NO new boot within 120s (running_since: ${AFTER:-<none>})."
    echo "The rescue boot.py is in flash from step 3 on, the device should be"
    echo "reachable over WiFi/WebREPL and report 'RESCUE-BOOT active' at boot."
    echo "$SCRIPT is still there and can be imported again."
    exit 1
fi
