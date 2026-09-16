#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "INSTALL=FAIL reason=root_required" >&2
    exit 1
fi

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
QUADLET_DIR=/etc/containers/systemd
BIN_DIR=/opt/akamai-mfa/bin
CONFIG_DIR=/opt/akamai-mfa/config

install -d -m 0755 "$QUADLET_DIR" "$BIN_DIR"
install -d -m 0700 \
    "$CONFIG_DIR/postgres-v2" \
    "$CONFIG_DIR/api-v2" \
    "$CONFIG_DIR/mcp-v2"

install_safe() {
    src="$1"
    dst="$2"
    mode="$3"

    if [ -e "$dst" ]; then
        if ! cmp -s "$src" "$dst"; then
            echo "INSTALL=FAIL reason=existing_file_differs path=$dst" >&2
            exit 1
        fi
        echo "UNCHANGED=$dst"
        return 0
    fi

    install -m "$mode" "$src" "$dst"
    echo "INSTALLED=$dst"
}

install_safe "$BASE_DIR/networks/akamai-mfa.network" "$QUADLET_DIR/akamai-mfa.network" 0644
install_safe "$BASE_DIR/networks/librechat.network" "$QUADLET_DIR/librechat.network" 0644

install_safe "$BASE_DIR/quadlets/akamai-mfa-postgres-v2.container" "$QUADLET_DIR/akamai-mfa-postgres-v2.container" 0644
install_safe "$BASE_DIR/quadlets/akamai-mfa-api-v2.container" "$QUADLET_DIR/akamai-mfa-api-v2.container" 0644
install_safe "$BASE_DIR/quadlets/akamai-mfa-mcp-v2.container" "$QUADLET_DIR/akamai-mfa-mcp-v2.container" 0644

install_safe "$BASE_DIR/bin/akamai-mfa-api-v2-entrypoint.sh" "$BIN_DIR/akamai-mfa-api-v2-entrypoint.sh" 0755
install_safe "$BASE_DIR/bin/wait-postgres-v2-ready.sh" "$BIN_DIR/wait-postgres-v2-ready.sh" 0755
install_safe "$BASE_DIR/bin/wait-api-v2-ready.sh" "$BIN_DIR/wait-api-v2-ready.sh" 0755
install_safe "$BASE_DIR/bin/wait-mcp-v2-ready.sh" "$BIN_DIR/wait-mcp-v2-ready.sh" 0755

# Examples only. install.sh deliberately does not create live environment files.
install -m 0600 "$BASE_DIR/env/postgres-v2.env.example" "$CONFIG_DIR/postgres-v2/postgres-v2.env.example"
install -m 0600 "$BASE_DIR/env/api-v2.env.example" "$CONFIG_DIR/api-v2/api-v2.env.example"
install -m 0600 "$BASE_DIR/env/mcp-v2.env.example" "$CONFIG_DIR/mcp-v2/mcp-v2.env.example"

systemctl daemon-reload

echo "INSTALL=PASS"
echo "NEXT=provision_runtime_env_and_podman_secrets_then_run_preflight"
