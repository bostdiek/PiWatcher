#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# deploy-base.sh
# Deploy PiWatcher base station files to a Pi 5 and install the systemd unit.

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SERVICE_SRC="${REPO_ROOT}/deploy/piwatcher-base.service"
readonly DEFAULT_FRAME_STORAGE_PATH="/home/bostdiek/piwatcher/frames"
readonly DEFAULT_UV_BIN="/home/bostdiek/.local/bin/uv"

declare -a SSH_OPTIONS=(-4)
cleanup_remote=""
cleanup_control_path=""
cleanup_tmp_dir=""

err() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: deploy/deploy-base.sh <pi5-host> [pi5-user]

Environment overrides:
  BASE_PROJECT_DIR     Remote repo path. Defaults to /home/<user>/Projects/PiWatcher
  FRAME_STORAGE_PATH   Frame storage directory to create/chown before startup
  UV_BIN               Remote uv executable. Defaults to /home/<user>/.local/bin/uv
  ENABLE_BASE_SERVICE  Defaults to false
  START_BASE           Defaults to false
USAGE
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    err "'${command_name}' is required"
  fi
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

  local base_host="${1:-}"
  local base_user="${2:-${BASE_USER:-bostdiek}}"

  if [[ -z "${base_host}" ]]; then
    usage
    exit 1
  fi

  require_command ssh
  require_command rsync

  [[ -f "${SERVICE_SRC}" ]] || err "Service file not found at ${SERVICE_SRC}"

  local remote="${base_user}@${base_host}"
  local project_dir="${BASE_PROJECT_DIR:-/home/${base_user}/Projects/PiWatcher}"
  local frame_storage_path="${FRAME_STORAGE_PATH:-${DEFAULT_FRAME_STORAGE_PATH}}"
  local uv_bin="${UV_BIN:-/home/${base_user}/.local/bin/uv}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local control_path="${tmp_dir}/ssh-control"
  cleanup_remote="${remote}"
  cleanup_control_path="${control_path}"
  cleanup_tmp_dir="${tmp_dir}"
  trap cleanup EXIT

  printf "Deploying PiWatcher base to %s:%s\n" \
    "${remote}" \
    "${project_dir}"

  open_ssh_master "${remote}" "${control_path}"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "mkdir -p '${project_dir}'"

  rsync \
    -avz \
    --delete \
    --exclude .git \
    --exclude .env \
    --exclude .venv \
    --exclude .ruff_cache \
    --exclude .pytest_cache \
    --exclude .mypy_cache \
    --exclude .ty \
    --exclude .vscode \
    --exclude '._*' \
    --exclude ._bryan \
    --exclude dist \
    --exclude build \
    --exclude __pycache__ \
    --exclude tmp \
    -e "ssh -4 -o ControlPath=${control_path}" \
    "${REPO_ROOT}/" \
    "${remote}:${project_dir}/"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "sudo install -d -o '${base_user}' -g '${base_user}' '${frame_storage_path}'"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "test -x '${uv_bin}' && cd '${project_dir}' && docker compose up -d postgres && cd packages/base && '${uv_bin}' run alembic upgrade head"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "sudo cp '${project_dir}/deploy/piwatcher-base.service' /etc/systemd/system/piwatcher-base.service && sudo systemctl daemon-reload"

  if [[ "${ENABLE_BASE_SERVICE:-false}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl enable piwatcher-base.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl disable piwatcher-base.service >/dev/null 2>&1 || true"
  fi

  if [[ "${START_BASE:-false}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl restart piwatcher-base.service && sudo systemctl status --no-pager -l piwatcher-base.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl stop piwatcher-base.service >/dev/null 2>&1 || true"
    printf "Base service is deployed but not started. Use START_BASE=true to start it.\n"
  fi
}

main "$@"
