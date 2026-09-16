#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROD_DIR=$(CDPATH= cd -- "$BASE_DIR/.." && pwd)
REPO_ROOT=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
RESULT_LABEL=DEPLOYMENT
. "$BASE_DIR/common.sh"

MODE=''
CONFIG=/etc/akamai-mfa/production.conf
SECRETS_DIR=/run/akamai-mfa-secrets
AUTHFILE=''
ALLOW_PLATFORM_DRIFT=0
SKIP_NETWORK_CHECK=0
APPROVE_START=0
REUSE_EXISTING_SECRETS=0
ROLLBACK_ARMED=0

usage() {
    cat <<'EOF'
usage:
  deploy-production.sh --check-only [options]
  deploy-production.sh --deploy [options] [--approve-start]

options:
  --config FILE                 default: /etc/akamai-mfa/production.conf
  --secrets-dir DIR             default: /run/akamai-mfa-secrets
  --authfile FILE               root-owned Podman authfile for private GHCR
  --allow-platform-drift        explicitly allow host outside validated baseline
  --skip-network-check          explicitly skip github.com/ghcr.io connectivity check
  --reuse-existing-secrets      reuse already-created Podman secrets
  --approve-start               allow services to be enabled/started after preflight
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check-only) MODE=check ;;
        --deploy) MODE=deploy ;;
        --config)
            shift; [ "$#" -gt 0 ] || fail missing_config_argument; CONFIG=$1 ;;
        --secrets-dir)
            shift; [ "$#" -gt 0 ] || fail missing_secrets_dir_argument; SECRETS_DIR=$1 ;;
        --authfile)
            shift; [ "$#" -gt 0 ] || fail missing_authfile_argument; AUTHFILE=$1 ;;
        --allow-platform-drift) ALLOW_PLATFORM_DRIFT=1 ;;
        --skip-network-check) SKIP_NETWORK_CHECK=1 ;;
        --reuse-existing-secrets) REUSE_EXISTING_SECRETS=1 ;;
        --approve-start) APPROVE_START=1 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown_argument_$1" ;;
    esac
    shift
done

[ -n "$MODE" ] || fail mode_required
require_root
for cmd in git podman systemctl; do require_cmd "$cmd"; done

on_exit() {
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$ROLLBACK_ARMED" -eq 1 ]; then
        echo "DEPLOYMENT_ROLLBACK=START"
        sh "$BASE_DIR/rollback.sh" || true
    fi
    exit "$rc"
}
trap on_exit EXIT HUP INT TERM

host_args=''
[ "$ALLOW_PLATFORM_DRIFT" -eq 1 ] && host_args="$host_args --allow-platform-drift"
[ "$SKIP_NETWORK_CHECK" -eq 1 ] && host_args="$host_args --skip-network-check"
# shellcheck disable=SC2086
sh "$BASE_DIR/host-preflight.sh" $host_args

sh "$BASE_DIR/render-env.sh" --check-only --config "$CONFIG"

require_protected_file "$CONFIG"
expected_commit=$(get_config_value "$CONFIG" EXPECTED_REPO_COMMIT)
actual_commit=$(git -C "$REPO_ROOT" rev-parse HEAD)
[ "$actual_commit" = "$expected_commit" ] || fail repo_commit_mismatch
[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ] || fail repo_worktree_not_clean
echo "REPO_IDENTITY=PASS"

secret_check_args="--check-only --secrets-dir $SECRETS_DIR"
# Paths with whitespace are not supported by the automation interface.
case "$SECRETS_DIR$AUTHFILE$CONFIG" in
    *' '*) fail paths_with_spaces_not_supported ;;
esac
# shellcheck disable=SC2086
sh "$BASE_DIR/provision-secrets.sh" $secret_check_args

pull_check_args='--check-only'
[ -n "$AUTHFILE" ] && pull_check_args="$pull_check_args --authfile $AUTHFILE"
# shellcheck disable=SC2086
sh "$BASE_DIR/pull-images.sh" $pull_check_args

existing_active=0
for unit in akamai-mfa-postgres-v2.service akamai-mfa-api-v2.service akamai-mfa-mcp-v2.service; do
    if systemctl is-active --quiet "$unit" 2>/dev/null; then
        existing_active=1
        echo "TARGET_ACTIVE_UNIT=$unit"
    fi
done

if [ "$MODE" = check ]; then
    if [ "$existing_active" -eq 1 ]; then
        echo "TARGET_STATE=EXISTING_DEPLOYMENT"
    else
        echo "TARGET_STATE=NO_ACTIVE_V2_SERVICES"
    fi
    echo "CHECK_ONLY=PASS"
    trap - EXIT HUP INT TERM
    exit 0
fi

[ "$existing_active" -eq 0 ] || fail existing_active_v2_deployment_not_supported
for name in akamai-mfa-postgres-v2 akamai-mfa-api-v2 akamai-mfa-mcp-v2; do
    if podman container exists "$name" 2>/dev/null; then
        fail "existing_container_not_supported_$name"
    fi
done

pull_args=''
[ -n "$AUTHFILE" ] && pull_args="--authfile $AUTHFILE"
# shellcheck disable=SC2086
sh "$BASE_DIR/pull-images.sh" $pull_args

sh "$PROD_DIR/install.sh"
sh "$BASE_DIR/render-env.sh" --apply --config "$CONFIG"

secret_apply_args="--apply --secrets-dir $SECRETS_DIR"
[ "$REUSE_EXISTING_SECRETS" -eq 1 ] && secret_apply_args="$secret_apply_args --reuse-existing"
# shellcheck disable=SC2086
sh "$BASE_DIR/provision-secrets.sh" $secret_apply_args

sh "$PROD_DIR/preflight.sh"

if [ "$APPROVE_START" -ne 1 ]; then
    echo "DEPLOYMENT=READY_TO_START"
    echo "NEXT=rerun_with_--deploy_--approve-start_--reuse-existing-secrets"
    trap - EXIT HUP INT TERM
    exit 0
fi

ROLLBACK_ARMED=1
systemctl enable --now akamai-mfa-network.service
systemctl enable --now librechat-network.service
systemctl enable --now akamai-mfa-postgres-v2.service
/opt/akamai-mfa/bin/wait-postgres-v2-ready.sh

sh "$BASE_DIR/bootstrap-db.sh"

systemctl enable --now akamai-mfa-api-v2.service
/opt/akamai-mfa/bin/wait-api-v2-ready.sh

systemctl enable --now akamai-mfa-mcp-v2.service
/opt/akamai-mfa/bin/wait-mcp-v2-ready.sh

sh "$PROD_DIR/smoke.sh"

api_runtime_id=$(podman inspect akamai-mfa-api-v2 --format '{{.Image}}')
mcp_runtime_id=$(podman inspect akamai-mfa-mcp-v2 --format '{{.Image}}')
[ "$api_runtime_id" = "$API_ID" ] || fail api_runtime_image_id_mismatch
[ "$mcp_runtime_id" = "$MCP_ID" ] || fail mcp_runtime_image_id_mismatch

echo "RUNTIME_IMAGE_IDENTITY=PASS"
echo "DEPLOYMENT=PASS"
ROLLBACK_ARMED=0
trap - EXIT HUP INT TERM
