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
Usage: deploy/deploy-camera.sh <camera-host|camera-env-file> [camera-user]

Environment overrides:
  CAMERA_ENV_FILE        Optional env profile file. If set, values are loaded
                         before defaults. Host can come from CAMERA_HOST.
                         First argument may also be this file path.
  CAMERA_HOST            Camera host when using CAMERA_ENV_FILE
  CAMERA_USER            Camera user when not passed as positional argument
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
  ENABLE_CAMERA_SERVICE  Optional: true enables, false disables,
                         unset preserves current enabled/disabled state
  START_CAMERA           Optional: true restarts, false stops,
                         unset preserves current running/stopped state
USAGE
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    err "'${command_name}' is required"
  fi
}

read_env_value() {
  local env_file="$1"
  local key="$2"

  awk -F= -v key="${key}" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "${env_file}"
}

apply_env_default_from_file() {
  local env_file="$1"
  local key="$2"
  local value=""

  if [[ -n "${!key:-}" ]]; then
    return
  fi

  value="$(read_env_value "${env_file}" "${key}")"
  if [[ -z "${value}" ]]; then
    return
  fi

  printf -v "${key}" '%s' "${value}"
  export "${key}"
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

  local input_target="${1:-}"
  local camera_user_arg="${2:-}"
  local camera_env_file="${CAMERA_ENV_FILE:-}"
  local camera_host="${input_target}"
  local camera_user="${camera_user_arg:-${CAMERA_USER:-pi}}"

  if [[ -n "${input_target}" && -f "${input_target}" ]]; then
    camera_env_file="${input_target}"
    camera_host=""
  fi

  if [[ -n "${camera_env_file}" ]]; then
    [[ -f "${camera_env_file}" ]] || err "Camera env file not found at ${camera_env_file}"

    apply_env_default_from_file "${camera_env_file}" CAMERA_HOST
    apply_env_default_from_file "${camera_env_file}" CAMERA_USER
    apply_env_default_from_file "${camera_env_file}" CAMERA_ID
    apply_env_default_from_file "${camera_env_file}" SERVER_URL
    apply_env_default_from_file "${camera_env_file}" MOTION_THRESHOLD
    apply_env_default_from_file "${camera_env_file}" MIN_CHANGED_PCT
    apply_env_default_from_file "${camera_env_file}" CAPTURE_FPS
    apply_env_default_from_file "${camera_env_file}" CAPTURE_MIN_DURATION
    apply_env_default_from_file "${camera_env_file}" COOLDOWN_SECONDS
    apply_env_default_from_file "${camera_env_file}" HEARTBEAT_INTERVAL
    apply_env_default_from_file "${camera_env_file}" LORES_WIDTH
    apply_env_default_from_file "${camera_env_file}" LORES_HEIGHT
    apply_env_default_from_file "${camera_env_file}" MAIN_WIDTH
    apply_env_default_from_file "${camera_env_file}" MAIN_HEIGHT
    apply_env_default_from_file "${camera_env_file}" FRAME_QUEUE_DIR
    apply_env_default_from_file "${camera_env_file}" WIFI_POWER_SAVE
    apply_env_default_from_file "${camera_env_file}" WIFI_STARTUP_GRACE_SECONDS
    apply_env_default_from_file "${camera_env_file}" ENABLE_CAMERA_SERVICE
    apply_env_default_from_file "${camera_env_file}" START_CAMERA

    if [[ -z "${camera_host}" ]]; then
      camera_host="${CAMERA_HOST:-}"
    fi

    if [[ -z "${camera_user_arg}" ]]; then
      camera_user="${CAMERA_USER:-${camera_user}}"
    fi
  fi

  if [[ -z "${camera_host}" ]]; then
    usage
    exit 1
  fi

  require_command ssh
  require_command rsync
  require_command scp

  if [[ -n "${ENABLE_CAMERA_SERVICE:-}" ]] && [[ "${ENABLE_CAMERA_SERVICE}" != "true" ]] && [[ "${ENABLE_CAMERA_SERVICE}" != "false" ]]; then
    err "ENABLE_CAMERA_SERVICE must be true or false when set"
  fi

  if [[ -n "${START_CAMERA:-}" ]] && [[ "${START_CAMERA}" != "true" ]] && [[ "${START_CAMERA}" != "false" ]]; then
    err "START_CAMERA must be true or false when set"
  fi

  [[ -f "${ROOT_ENV}" ]] || err "Root .env not found at ${ROOT_ENV}"
  [[ -d "${CAMERA_SRC}" ]] || err "Camera source not found at ${CAMERA_SRC}"

  local api_key
  api_key="$(read_env_value "${ROOT_ENV}" PIWATCHER_API_KEY)"
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
  local setup_enable_override=""
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local control_path="${tmp_dir}/ssh-control"
  cleanup_remote="${remote}"
  cleanup_control_path="${control_path}"
  cleanup_tmp_dir="${tmp_dir}"
  trap cleanup EXIT

  local camera_env="${tmp_dir}/camera.env"
  write_camera_env "${camera_env}" "${camera_id}" "${server_url}" "${api_key}"

  if [[ -n "${ENABLE_CAMERA_SERVICE:-}" ]]; then
    setup_enable_override=" ENABLE_CAMERA_SERVICE=${ENABLE_CAMERA_SERVICE}"
  fi

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
    "chmod +x ~/setup-camera.sh && sudo env PIWATCHER_USER=${camera_user} PIWATCHER_HOME=/home/${camera_user}${setup_enable_override} ~/setup-camera.sh"

  if [[ "${START_CAMERA:-}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" "sudo systemctl restart piwatcher-camera.service && sudo systemctl status --no-pager piwatcher-camera.service"
  elif [[ "${START_CAMERA:-}" == "false" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" "sudo systemctl stop piwatcher-camera.service >/dev/null 2>&1 || true"
    printf "Camera service stopped after deploy (START_CAMERA=false).\n"
  else
    printf "Camera service run state preserved. Set START_CAMERA=true|false to override.\n"
  fi
}

main "$@"
