#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RESULT_LABEL=HOST_PREFLIGHT
. "$BASE_DIR/common.sh"

ALLOW_PLATFORM_DRIFT=0
SKIP_NETWORK_CHECK=0
HOST_PROFILE=validated-ol8.10

while [ "$#" -gt 0 ]; do
    case "$1" in
        --host-profile)
            shift
            [ "$#" -gt 0 ] || fail missing_host_profile_argument
            HOST_PROFILE=$1
            ;;
        --allow-platform-drift) ALLOW_PLATFORM_DRIFT=1 ;;
        --skip-network-check) SKIP_NETWORK_CHECK=1 ;;
        -h|--help)
            echo "usage: $0 [--host-profile validated-ol8.10|corporate-rhel8.7] [--allow-platform-drift] [--skip-network-check]"
            exit 0
            ;;
        *) fail "unknown_argument_$1" ;;
    esac
    shift
done

require_root
for cmd in podman systemctl timedatectl stat grep awk sed curl git cmp sha256sum df; do
    require_cmd "$cmd"
done

[ -r /etc/os-release ] || fail missing_os_release
# /etc/os-release is a root-owned operating-system metadata file.
. /etc/os-release

case "$HOST_PROFILE" in
    validated-ol8.10)
        EXPECTED_ID=ol
        EXPECTED_VERSION_ID=8.10
        EXPECTED_SELINUX=Enforcing
        ;;
    corporate-rhel8.7)
        EXPECTED_ID=rhel
        EXPECTED_VERSION_ID=8.7
        EXPECTED_SELINUX=Disabled
        ;;
    *) fail "unknown_host_profile_$HOST_PROFILE" ;;
esac

platform_ok=1
[ "${ID:-}" = "$EXPECTED_ID" ] || platform_ok=0
[ "${VERSION_ID:-}" = "$EXPECTED_VERSION_ID" ] || platform_ok=0
podman --version | grep -q '4\.9\.4-rhel' || platform_ok=0
systemctl --version | head -1 | grep -q '^systemd 239' || platform_ok=0

if [ "$platform_ok" -ne 1 ]; then
    if [ "$ALLOW_PLATFORM_DRIFT" -eq 1 ]; then
        echo "PLATFORM_BASELINE=DRIFT_ALLOWED profile=$HOST_PROFILE"
    else
        fail "platform_outside_profile_$HOST_PROFILE"
    fi
else
    echo "PLATFORM_BASELINE=PASS profile=$HOST_PROFILE"
fi

quadlet_generator=''
for p in \
    /usr/lib/systemd/system-generators/podman-system-generator \
    /usr/local/lib/systemd/system-generators/podman-system-generator
do
    if [ -x "$p" ]; then
        quadlet_generator=$p
        break
    fi
done
[ -n "$quadlet_generator" ] || fail quadlet_generator_missing
echo "QUADLET=PASS"

require_cmd getenforce
actual_selinux=$(getenforce)
[ "$actual_selinux" = "$EXPECTED_SELINUX" ] \
    || fail "selinux_state_${actual_selinux}_expected_${EXPECTED_SELINUX}_for_$HOST_PROFILE"
echo "SELINUX=PASS profile=$HOST_PROFILE state=$actual_selinux"

sync=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)
if [ "$sync" != yes ]; then
    timedatectl status 2>/dev/null | grep -q 'System clock synchronized: yes' \
        || fail system_clock_not_synchronized
fi
echo "TIME_SYNC=PASS"

storage_path=/
[ -d /var/lib/containers/storage ] && storage_path=/var/lib/containers/storage
avail_kb=$(df -Pk "$storage_path" | awk 'NR==2 {print $4}')
case "$avail_kb" in
    ''|*[!0-9]*) fail unable_to_read_storage_free_space ;;
esac
[ "$avail_kb" -ge 5242880 ] || fail storage_free_space_below_5GiB
echo "STORAGE=PASS"

if [ "$SKIP_NETWORK_CHECK" -eq 0 ]; then
    github_code=$(curl -L -sS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 20 https://github.com/ || true)
    case "$github_code" in
        200|301|302) ;;
        *) fail "github_connectivity_http_$github_code" ;;
    esac

    ghcr_code=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 20 https://ghcr.io/v2/ || true)
    case "$ghcr_code" in
        200|401) ;;
        *) fail "ghcr_connectivity_http_$ghcr_code" ;;
    esac
    echo "NETWORK_CONNECTIVITY=PASS"
else
    echo "NETWORK_CONNECTIVITY=SKIPPED"
fi

echo "HOST_PREFLIGHT=PASS"
