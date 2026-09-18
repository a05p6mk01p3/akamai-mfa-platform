#!/usr/bin/env bash
set -euo pipefail

API_ENV="${API_ENV:-/opt/akamai-mfa/config/api-v2/api-v2.env}"
MCP_ENV="${MCP_ENV:-/opt/akamai-mfa/config/mcp-v2/mcp-v2.env}"
API_SERVICE="${API_SERVICE:-akamai-mfa-api-v2.service}"
MCP_SERVICE="${MCP_SERVICE:-akamai-mfa-mcp-v2.service}"
API_CONTAINER="${API_CONTAINER:-akamai-mfa-api-v2}"
MCP_CONTAINER="${MCP_CONTAINER:-akamai-mfa-mcp-v2}"
INSTALLED_SELF="${INSTALLED_SELF:-/opt/akamai-mfa/bin/akamai-mfa-destructive-mode.sh}"
TIMER_STATE="${TIMER_STATE:-/run/akamai-mfa-destructive-auto-disable.unit}"
LOCK_FILE="${LOCK_FILE:-/run/akamai-mfa-destructive-mode.lock}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/akamai-mfa/backups/destructive-mode}"

SAFE_API_BACKEND="simulation"
LIVE_API_BACKEND="live"
SAFE_MCP_MODE="disabled"
ENABLED_MCP_MODE="enabled"
CONFIRM_TOKEN="ENABLE-AKAMAI-MFA-DESTRUCTIVE"
PERSISTENT_CONFIRM_TOKEN="ENABLE-AKAMAI-MFA-DESTRUCTIVE-PERSISTENT"
FROZEN_API_DIGEST="sha256:5d79ba99978e5309a26f2f6aa1285b8c2da11547e47b1e55169e6f9252c6a8af"

log() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'USAGE'
Usage:
  akamai-mfa-destructive-mode status
  akamai-mfa-destructive-mode enable --minutes N --confirm ENABLE-AKAMAI-MFA-DESTRUCTIVE
  akamai-mfa-destructive-mode enable --persistent --confirm ENABLE-AKAMAI-MFA-DESTRUCTIVE-PERSISTENT
  akamai-mfa-destructive-mode disable [--auto]

CS12 semantics:
  safe baseline: API EXECUTION_BACKEND=simulation; MCP destructive mode=disabled
  bounded enable: API EXECUTION_BACKEND=live; MCP destructive mode=enabled
                  with a verified auto-disable timer (5..120 minutes)
  persistent enable: API EXECUTION_BACKEND=live; MCP destructive mode=enabled
                     without an auto-disable timer; remains enabled until explicit disable
  enable is refused unless the production API image supports the CS12 live backend
  disable is fail-closed and restores the safe baseline without a domain selector
USAGE
}

require_root() {
    [[ "$(id -u)" -eq 0 ]] || die "must run as root"
}

require_commands() {
    local cmd
    for cmd in awk cat chmod chown cp date flock grep mkdir mktemp mv podman readlink rm sleep systemctl systemd-run; do
        command -v "$cmd" >/dev/null 2>&1 || die "required command unavailable: $cmd"
    done
}

read_env() {
    local file="$1" key="$2"
    awk -F= -v key="$key" '$1 == key { print substr($0, length($1) + 2); found=1; exit } END { if (!found) exit 2 }' "$file"
}

set_env() {
    local file="$1" key="$2" value="$3" tmp
    if [[ ! -f "$file" ]]; then
        printf 'ERROR: env file unavailable: %s\n' "$file" >&2
        return 1
    fi
    if ! tmp="$(mktemp "${file}.tmp.XXXXXX")"; then
        printf 'ERROR: could not create temporary file for %s\n' "$file" >&2
        return 1
    fi

    if ! awk -F= -v key="$key" -v value="$value" '
        BEGIN { count=0 }
        $1 == key { $0=key "=" value; count++ }
        { print }
        END { if (count != 1) exit 42 }
    ' "$file" >"$tmp"; then
        rm -f "$tmp"
        printf 'ERROR: expected exactly one %s entry in %s\n' "$key" "$file" >&2
        return 1
    fi

    if ! chmod --reference="$file" "$tmp" || \
       ! chown --reference="$file" "$tmp" || \
       ! mv -f "$tmp" "$file"; then
        rm -f "$tmp"
        printf 'ERROR: could not atomically update %s in %s\n' "$key" "$file" >&2
        return 1
    fi
}

runtime_env() {
    local container="$1" key="$2"
    podman inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
        awk -F= -v key="$key" '$1 == key && !found { print substr($0, length($1) + 2); found=1 } END { if (!found) exit 2 }'
}

wait_active() {
    local service="$1" i
    for ((i=0; i<30; i++)); do
        systemctl is-active --quiet "$service" && return 0
        sleep 1
    done
    return 1
}

wait_runtime_value() {
    local container="$1" key="$2" expected="$3" i value
    for ((i=0; i<30; i++)); do
        value="$(runtime_env "$container" "$key" 2>/dev/null || true)"
        [[ "$value" == "$expected" ]] && return 0
        sleep 1
    done
    return 1
}

wait_api_ready_backend() {
    local expected="$1" i
    for ((i=0; i<30; i++)); do
        if podman exec "$API_CONTAINER" python -c '
import json, sys, urllib.request
expected = sys.argv[1]
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=2) as r:
        data = json.load(r)
    ok = (
        r.status == 200
        and data.get("status") == "ready"
        and data.get("execution_backend") == expected
    )
except Exception:
    ok = False
raise SystemExit(0 if ok else 1)
' "$expected" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

backup_configs() {
    local action="$1" dir

    if ! mkdir -p "$BACKUP_ROOT" || ! chmod 0700 "$BACKUP_ROOT"; then
        printf 'ERROR: could not prepare protected backup root\n' >&2
        return 1
    fi

    if ! dir="$(mktemp -d "$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${action}.XXXXXX")"; then
        printf 'ERROR: could not create unique protected configuration backup\n' >&2
        return 1
    fi

    if ! chmod 0700 "$dir" || \
       ! cp -p "$API_ENV" "$dir/api-v2.env" || \
       ! cp -p "$MCP_ENV" "$dir/mcp-v2.env" || \
       ! chmod 0600 "$dir/api-v2.env" "$dir/mcp-v2.env"; then
        rm -rf "$dir"
        printf 'ERROR: could not create protected configuration backup\n' >&2
        return 1
    fi

    log "configuration backup created: $dir"
}

cancel_auto_disable_timer() {
    local unit=""
    if [[ -s "$TIMER_STATE" ]]; then
        unit="$(cat "$TIMER_STATE" 2>/dev/null || true)"
    fi

    if [[ -n "$unit" ]]; then
        systemctl stop "${unit}.timer" >/dev/null 2>&1 || true
        systemctl reset-failed "${unit}.timer" >/dev/null 2>&1 || true
    fi

    rm -f "$TIMER_STATE"
}

schedule_auto_disable() {
    local minutes="$1" unit
    unit="akamai-mfa-destructive-auto-disable-$(date +%s)"

    if ! systemd-run --quiet \
        --unit="$unit" \
        --on-active="${minutes}m" \
        "$INSTALLED_SELF" disable --auto; then
        return 1
    fi

    if ! systemctl is-active --quiet "${unit}.timer"; then
        systemctl stop "${unit}.timer" >/dev/null 2>&1 || true
        return 1
    fi

    if ! printf '%s\n' "$unit" >"$TIMER_STATE" || ! chmod 0600 "$TIMER_STATE"; then
        systemctl stop "${unit}.timer" >/dev/null 2>&1 || true
        rm -f "$TIMER_STATE"
        return 1
    fi
    log "auto-disable timer verified active: ${unit}.timer (${minutes} minute(s))"
}

api_supports_live_backend() {
    podman exec \
        -e AKAMAI_CLIENT_TOKEN=cs12-probe \
        -e AKAMAI_CLIENT_SECRET=cs12-probe \
        -e AKAMAI_ACCESS_TOKEN=cs12-probe \
        -e EXECUTION_BACKEND=live \
        "$API_CONTAINER" \
        python -c '
from app.config import Settings
s = Settings.from_env()
raise SystemExit(
    0 if (
        s.execution_backend == "live"
        and s.execution_framework_enabled
        and s.destructive_operations_enabled
    ) else 1
)
' >/dev/null 2>&1
}

preflight_enable() {
    local api_file mcp_file api_runtime mcp_runtime api_image

    [[ -x "$INSTALLED_SELF" ]] || die "installed control script unavailable or not executable: $INSTALLED_SELF"
    [[ "$(readlink -f "${BASH_SOURCE[0]}")" == "$(readlink -f "$INSTALLED_SELF")" ]] || \
        die "enable must be invoked from installed control script: $INSTALLED_SELF"

    [[ -f "$API_ENV" ]] || die "API env file unavailable"
    [[ -f "$MCP_ENV" ]] || die "MCP env file unavailable"
    systemctl is-active --quiet "$API_SERVICE" || die "$API_SERVICE is not active"
    systemctl is-active --quiet "$MCP_SERVICE" || die "$MCP_SERVICE is not active"

    api_file="$(read_env "$API_ENV" EXECUTION_BACKEND)"
    mcp_file="$(read_env "$MCP_ENV" MCP_DESTRUCTIVE_EXECUTION_MODE)"
    api_runtime="$(runtime_env "$API_CONTAINER" EXECUTION_BACKEND)"
    mcp_runtime="$(runtime_env "$MCP_CONTAINER" MCP_DESTRUCTIVE_EXECUTION_MODE)"

    [[ "$api_file" == "$SAFE_API_BACKEND" ]] || die "API env is not in simulation; run disable first"
    [[ "$mcp_file" == "$SAFE_MCP_MODE" ]] || die "MCP env is not disabled; run disable first"
    [[ "$api_runtime" == "$SAFE_API_BACKEND" ]] || die "API runtime is not in simulation; run disable first"
    [[ "$mcp_runtime" == "$SAFE_MCP_MODE" ]] || die "MCP runtime is not disabled; run disable first"
    [[ ! -s "$TIMER_STATE" ]] || die "auto-disable timer state already exists; run disable first"

    api_image="$(podman inspect "$API_CONTAINER" --format '{{.ImageName}}')"
    if [[ "$api_image" == *"$FROZEN_API_DIGEST"* ]]; then
        die "production API is still the frozen v2.0.0 image and does not support EXECUTION_BACKEND=live"
    fi

    api_supports_live_backend || die "production API image does not support the CS12 live backend semantics"
}

force_mcp_safe_or_stop() {
    if set_env "$MCP_ENV" MCP_DESTRUCTIVE_EXECUTION_MODE "$SAFE_MCP_MODE" && \
       systemctl restart "$MCP_SERVICE" && \
       wait_active "$MCP_SERVICE" && \
       wait_runtime_value "$MCP_CONTAINER" MCP_DESTRUCTIVE_EXECUTION_MODE "$SAFE_MCP_MODE"; then
        return 0
    fi

    printf 'CRITICAL: MCP safe state could not be verified; stopping %s\n' "$MCP_SERVICE" >&2
    systemctl stop "$MCP_SERVICE" >/dev/null 2>&1 || true
    return 1
}

force_api_safe_or_stop() {
    if set_env "$API_ENV" EXECUTION_BACKEND "$SAFE_API_BACKEND" && \
       systemctl restart "$API_SERVICE" && \
       wait_active "$API_SERVICE" && \
       wait_runtime_value "$API_CONTAINER" EXECUTION_BACKEND "$SAFE_API_BACKEND" && \
       wait_api_ready_backend "$SAFE_API_BACKEND"; then
        return 0
    fi

    printf 'CRITICAL: API safe state could not be verified; stopping %s\n' "$API_SERVICE" >&2
    systemctl stop "$API_SERVICE" >/dev/null 2>&1 || true
    return 1
}

rollback_enable() {
    local failed=0

    log "ROLLBACK: restoring safe baseline"

    if ! force_mcp_safe_or_stop; then
        failed=1
    fi

    if ! force_api_safe_or_stop; then
        failed=1
    fi

    if [[ "$failed" -ne 0 ]]; then
        printf 'CRITICAL: rollback verification failed; affected service(s) stopped; timer state retained\n' >&2
        status_mode || true
        return 1
    fi

    cancel_auto_disable_timer
    log "ROLLBACK: safe baseline verified"
}

abort_enable() {
    local reason="$1"
    if rollback_enable; then
        die "$reason; safe baseline restored"
    fi
    die "$reason; rollback verification failed"
}

status_mode() {
    local api_file mcp_file api_runtime mcp_runtime timer_status="none" unit=""
    api_file="$(read_env "$API_ENV" EXECUTION_BACKEND 2>/dev/null || echo unavailable)"
    mcp_file="$(read_env "$MCP_ENV" MCP_DESTRUCTIVE_EXECUTION_MODE 2>/dev/null || echo unavailable)"
    api_runtime="$(runtime_env "$API_CONTAINER" EXECUTION_BACKEND 2>/dev/null || echo unavailable)"
    mcp_runtime="$(runtime_env "$MCP_CONTAINER" MCP_DESTRUCTIVE_EXECUTION_MODE 2>/dev/null || echo unavailable)"

    if [[ -s "$TIMER_STATE" ]]; then
        unit="$(cat "$TIMER_STATE" 2>/dev/null || true)"
        if [[ -n "$unit" ]] && systemctl is-active --quiet "${unit}.timer"; then
            timer_status="active:${unit}.timer"
        else
            timer_status="stale"
        fi
    fi

    printf 'API_FILE=%s\n' "$api_file"
    printf 'API_RUNTIME=%s\n' "$api_runtime"
    printf 'MCP_FILE=%s\n' "$mcp_file"
    printf 'MCP_RUNTIME=%s\n' "$mcp_runtime"
    printf 'AUTO_DISABLE_TIMER=%s\n' "$timer_status"

    if [[ "$api_file" == "$SAFE_API_BACKEND" && "$api_runtime" == "$SAFE_API_BACKEND" && \
          "$mcp_file" == "$SAFE_MCP_MODE" && "$mcp_runtime" == "$SAFE_MCP_MODE" && \
          "$timer_status" == "none" ]]; then
        printf 'DESTRUCTIVE_STATE=DISABLED\n'
    elif [[ "$api_file" == "$LIVE_API_BACKEND" && "$api_runtime" == "$LIVE_API_BACKEND" && \
            "$mcp_file" == "$ENABLED_MCP_MODE" && "$mcp_runtime" == "$ENABLED_MCP_MODE" && \
            "$timer_status" == active:* ]]; then
        printf 'DESTRUCTIVE_STATE=ENABLED_BOUNDED\n'
    elif [[ "$api_file" == "$LIVE_API_BACKEND" && "$api_runtime" == "$LIVE_API_BACKEND" && \
            "$mcp_file" == "$ENABLED_MCP_MODE" && "$mcp_runtime" == "$ENABLED_MCP_MODE" && \
            "$timer_status" == "none" ]]; then
        printf 'DESTRUCTIVE_STATE=ENABLED_PERSISTENT\n'
    else
        printf 'DESTRUCTIVE_STATE=INCONSISTENT\n'
        return 2
    fi
}

enable_mode() {
    local mode="$1" minutes="$2" confirm="$3"

    case "$mode" in
        bounded)
            [[ "$confirm" == "$CONFIRM_TOKEN" ]] || die "explicit bounded confirmation missing"
            [[ "$minutes" =~ ^[0-9]+$ ]] || die "--minutes must be an integer"
            (( minutes >= 5 && minutes <= 120 )) || die "--minutes must be between 5 and 120"
            ;;
        persistent)
            [[ "$confirm" == "$PERSISTENT_CONFIRM_TOKEN" ]] || \
                die "explicit persistent confirmation missing"
            [[ -z "$minutes" ]] || die "persistent mode does not accept --minutes"
            ;;
        *)
            die "internal enable mode is invalid"
            ;;
    esac

    preflight_enable
    backup_configs "enable-${mode}" || die "could not create pre-enable configuration backup"

    if [[ "$mode" == "bounded" ]]; then
        if ! schedule_auto_disable "$minutes"; then
            cancel_auto_disable_timer
            die "could not create and verify auto-disable timer; destructive mode remains disabled"
        fi
    else
        log "persistent destructive mode requested: no auto-disable timer will be created"
    fi

    log "enabling API live backend while MCP remains disabled"
    if ! set_env "$API_ENV" EXECUTION_BACKEND "$LIVE_API_BACKEND" || \
       ! systemctl restart "$API_SERVICE" || \
       ! wait_active "$API_SERVICE" || \
       ! wait_runtime_value "$API_CONTAINER" EXECUTION_BACKEND "$LIVE_API_BACKEND" || \
       ! wait_api_ready_backend "$LIVE_API_BACKEND"; then
        abort_enable "API failed to enter verified live backend"
    fi

    log "enabling MCP destructive master gate"
    if ! set_env "$MCP_ENV" MCP_DESTRUCTIVE_EXECUTION_MODE "$ENABLED_MCP_MODE" || \
       ! systemctl restart "$MCP_SERVICE" || \
       ! wait_active "$MCP_SERVICE" || \
       ! wait_runtime_value "$MCP_CONTAINER" MCP_DESTRUCTIVE_EXECUTION_MODE "$ENABLED_MCP_MODE"; then
        abort_enable "MCP failed to enter enabled mode"
    fi

    if [[ "$mode" == "bounded" ]]; then
        log "destructive mode enabled for a bounded ${minutes}-minute window"
    else
        log "destructive mode enabled persistently until explicit disable"
    fi
    status_mode
}

disable_mode() {
    local source="${1:-manual}" failed=0

    if [[ "$source" != "auto" ]]; then
        backup_configs "disable-${source}" || log "WARNING: backup failed; continuing fail-closed disable"
    fi

    log "requesting safe baseline: MCP=disabled API=simulation"

    if ! force_mcp_safe_or_stop; then
        failed=1
    fi

    if ! force_api_safe_or_stop; then
        failed=1
    fi

    if [[ "$failed" -ne 0 ]]; then
        status_mode || true
        die "safe baseline could not be verified; affected service(s) stopped and timer state retained"
    fi

    cancel_auto_disable_timer
    log "safe baseline verified"
    status_mode
}

main() {
    local command="${1:-}"
    shift || true

    require_root
    require_commands

    exec 9>"$LOCK_FILE"
    flock -n 9 || die "another destructive-mode control action is already running"

    case "$command" in
        status)
            [[ "$#" -eq 0 ]] || die "status accepts no arguments"
            status_mode
            ;;
        enable)
            local minutes="" confirm="" persistent=0
            while [[ "$#" -gt 0 ]]; do
                case "$1" in
                    --minutes)
                        [[ "$#" -ge 2 ]] || die "--minutes requires a value"
                        minutes="$2"
                        shift 2
                        ;;
                    --persistent)
                        [[ "$persistent" -eq 0 ]] || die "--persistent specified more than once"
                        persistent=1
                        shift
                        ;;
                    --confirm)
                        [[ "$#" -ge 2 ]] || die "--confirm requires a value"
                        confirm="$2"
                        shift 2
                        ;;
                    *)
                        die "unknown enable argument: $1"
                        ;;
                esac
            done
            if [[ "$persistent" -eq 1 ]]; then
                [[ -z "$minutes" ]] || die "--persistent and --minutes are mutually exclusive"
                enable_mode persistent "" "$confirm"
            else
                [[ -n "$minutes" ]] || die "--minutes is required unless --persistent is used"
                enable_mode bounded "$minutes" "$confirm"
            fi
            ;;
        disable)
            if [[ "$#" -eq 0 ]]; then
                disable_mode manual
            elif [[ "$#" -eq 1 && "$1" == "--auto" ]]; then
                disable_mode auto
            else
                die "disable accepts only optional --auto"
            fi
            ;;
        -h|--help|help|"")
            usage
            ;;
        *)
            die "unknown command: $command"
            ;;
    esac
}

main "$@"
