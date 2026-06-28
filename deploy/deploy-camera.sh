#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# deploy-camera.sh
# Generate camera configuration locally and deploy a PiWatcher camera node.

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_ENV="${REPO_ROOT}/.env"
readonly CAMERA_SRC="${REPO_ROOT}/packages/camera/src/piwatcher_camera"
readonly SERVICE_SRC="${REPO_ROOT}/deploy/piwatcher-camera.service"
readonly SETUP_SRC="${REPO_ROOT}/deploy/setup-camera.sh"

cleanup_remote=""
cleanup_control_path=""
cleanup_tmp_dir=""
declare -a SSH_OPTIONS=(-4)

err() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: deploy/deploy-camera.sh <camera-host> [camera-user]

Environment overrides:
  CAMERA_ID              Defaults to host name without .local
  SERVER_URL             Defaults to http://<local-wifi-ip>:8000
  MOTION_THRESHOLD       Defaults to 7.0
  MIN_CHANGED_PCT        Defaults to 2.0
  CAPTURE_FPS            Defaults to 2.0
  CAPTURE_MIN_DURATION   Defaults to 10.0
  COOLDOWN_SECONDS       Defaults to 5.0
  HEARTBEAT_INTERVAL     Defaults to 900
  LORES_WIDTH            Defaults to 160
  LORES_HEIGHT           Defaults to 120
  MAIN_WIDTH             Defaults to 1024
  MAIN_HEIGHT            Defaults to 1024
  FRAME_QUEUE_DIR        Defaults to /tmp/piwatcher/frames
  WIFI_POWER_SAVE        Defaults to false for local deploys
  WIFI_STARTUP_GRACE_SECONDS Defaults to 600
  ENABLE_CAMERA_SERVICE  Defaults to false
  START_CAMERA           Defaults to false
USAGE
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    err "'${command_name}' is required"
  fi
}

read_env_value() {
  local key="$1"

  awk -F= -v key="${key}" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "${ROOT_ENV}"
}

local_wifi_ip() {
  if command -v ipconfig >/dev/null 2>&1; then
    ipconfig getifaddr en0
    return
  fi

  hostname -I | awk '{print $1}'
}

write_camera_env() {
  local env_path="$1"
  local camera_id="$2"
  local server_url="$3"
  local api_key="$4"

  cat >"${env_path}" <<EOF
CAMERA_ID=${camera_id}
SERVER_URL=${server_url}
PIWATCHER_API_KEY=${api_key}
MOTION_THRESHOLD=${MOTION_THRESHOLD:-7.0}
MIN_CHANGED_PCT=${MIN_CHANGED_PCT:-2.0}
CAPTURE_FPS=${CAPTURE_FPS:-2.0}
CAPTURE_MIN_DURATION=${CAPTURE_MIN_DURATION:-10.0}
COOLDOWN_SECONDS=${COOLDOWN_SECONDS:-5.0}
HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-900}
LORES_WIDTH=${LORES_WIDTH:-160}
LORES_HEIGHT=${LORES_HEIGHT:-120}
MAIN_WIDTH=${MAIN_WIDTH:-1024}
MAIN_HEIGHT=${MAIN_HEIGHT:-1024}
FRAME_QUEUE_DIR=${FRAME_QUEUE_DIR:-/tmp/piwatcher/frames}
WIFI_POWER_SAVE=${WIFI_POWER_SAVE:-false}
WIFI_STARTUP_GRACE_SECONDS=${WIFI_STARTUP_GRACE_SECONDS:-600}
EOF
}

open_ssh_master() {
  local remote="$1"
  local control_path="$2"

  ssh \
    "${SSH_OPTIONS[@]}" \
    -MNf \
    -o ControlMaster=yes \
    -o ControlPath="${control_path}" \
    -o ControlPersist=10m \
    "${remote}"
}

close_ssh_master() {
  local remote="$1"
  local control_path="$2"

  ssh \
    "${SSH_OPTIONS[@]}" \
    -o ControlPath="${control_path}" \
    -O exit \
    "${remote}" >/dev/null 2>&1 || true
}

cleanup() {
  if [[ -n "${cleanup_remote}" && -n "${cleanup_control_path}" ]]; then
    close_ssh_master "${cleanup_remote}" "${cleanup_control_path}"
  fi

  if [[ -n "${cleanup_tmp_dir}" ]]; then
    rm -rf "${cleanup_tmp_dir}"
  fi
}

main() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  local camera_host="${1:-}"
  local camera_user="${2:-${CAMERA_USER:-pi}}"

  if [[ -z "${camera_host}" ]]; then
    usage
    exit 1
  fi

  require_command ssh
  require_command rsync
  require_command scp

  [[ -f "${ROOT_ENV}" ]] || err "Root .env not found at ${ROOT_ENV}"
  [[ -d "${CAMERA_SRC}" ]] || err "Camera source not found at ${CAMERA_SRC}"

  local api_key
  api_key="$(read_env_value PIWATCHER_API_KEY)"
  [[ -n "${api_key}" ]] || err "PIWATCHER_API_KEY is missing from ${ROOT_ENV}"

  local server_url="${SERVER_URL:-}"
  if [[ -z "${server_url}" ]]; then
    local local_ip
    local_ip="$(local_wifi_ip)"
    [[ -n "${local_ip}" ]] || err "Could not detect local Wi-Fi IP"
    server_url="http://${local_ip}:8000"
  fi

  local camera_id="${CAMERA_ID:-${camera_host%.local}}"
  local remote="${camera_user}@${camera_host}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local control_path="${tmp_dir}/ssh-control"
  cleanup_remote="${remote}"
  cleanup_control_path="${control_path}"
  cleanup_tmp_dir="${tmp_dir}"
  trap cleanup EXIT

  local camera_env="${tmp_dir}/camera.env"
  write_camera_env "${camera_env}" "${camera_id}" "${server_url}" "${api_key}"

  printf "Deploying camera '%s' to %s with server %s\n" \
    "${camera_id}" \
    "${remote}" \
    "${server_url}"

  open_ssh_master "${remote}" "${control_path}"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" "mkdir -p ~/piwatcher/deploy"
  rsync \
    -avz \
    --delete \
    -e "ssh -4 -o ControlPath=${control_path}" \
    "${CAMERA_SRC}" \
    "${remote}:~/piwatcher/"
  scp "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" \
    "${SETUP_SRC}" \
    "${remote}:~/setup-camera.sh"
  scp "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" \
    "${SERVICE_SRC}" \
    "${remote}:~/piwatcher/deploy/piwatcher-camera.service"
  scp "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" \
    "${camera_env}" \
    "${remote}:~/piwatcher/.env"
  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "chmod +x ~/setup-camera.sh && sudo env PIWATCHER_USER=${camera_user} PIWATCHER_HOME=/home/${camera_user} ENABLE_CAMERA_SERVICE=${ENABLE_CAMERA_SERVICE:-false} ~/setup-camera.sh"

  if [[ "${START_CAMERA:-false}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" "sudo systemctl restart piwatcher-camera.service && sudo systemctl status --no-pager piwatcher-camera.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" "sudo systemctl stop piwatcher-camera.service >/dev/null 2>&1 || true"
    printf "Camera service is deployed but not started. Use START_CAMERA=true to start it.\n"
  fi
}

main "$@"
