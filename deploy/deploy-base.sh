#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# deploy-base.sh
# Deploy PiWatcher base station files to a Pi 5 and install the systemd unit.

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SERVICE_SRC="${REPO_ROOT}/deploy/piwatcher-base.service"
readonly DEFAULT_BASE_ENV_FILE="${REPO_ROOT}/pi5.env"
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
  BASE_ENV_FILE        Local env file copied to remote .env when present. Defaults to pi5.env
  FRAME_STORAGE_PATH   Frame storage directory to create/chown before startup
  UV_BIN               Remote uv executable. Defaults to /home/<user>/.local/bin/uv
  ENABLE_BASE_SERVICE  true|false|preserve (default: preserve)
  START_BASE           true|false|preserve (default: preserve)
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
  require_command scp

  [[ -f "${SERVICE_SRC}" ]] || err "Service file not found at ${SERVICE_SRC}"

  local remote="${base_user}@${base_host}"
  local project_dir="${BASE_PROJECT_DIR:-/home/${base_user}/Projects/PiWatcher}"
  local base_env_file="${BASE_ENV_FILE:-${DEFAULT_BASE_ENV_FILE}}"
  local enable_base_service="${ENABLE_BASE_SERVICE:-preserve}"
  local start_base="${START_BASE:-preserve}"
  local frame_storage_path="${FRAME_STORAGE_PATH:-${DEFAULT_FRAME_STORAGE_PATH}}"
  if [[ -z "${FRAME_STORAGE_PATH:-}" && -f "${base_env_file}" ]]; then
    frame_storage_path="$(read_env_value "${base_env_file}" FRAME_STORAGE_PATH)"
    frame_storage_path="${frame_storage_path:-${DEFAULT_FRAME_STORAGE_PATH}}"
  fi
  local uv_bin="${UV_BIN:-/home/${base_user}/.local/bin/uv}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local control_path="${tmp_dir}/ssh-control"
  cleanup_remote="${remote}"
  cleanup_control_path="${control_path}"
  cleanup_tmp_dir="${tmp_dir}"
  trap cleanup EXIT

  case "${enable_base_service}" in
    true|false|preserve) ;;
    *) err "ENABLE_BASE_SERVICE must be true, false, or preserve" ;;
  esac

  case "${start_base}" in
    true|false|preserve) ;;
    *) err "START_BASE must be true, false, or preserve" ;;
  esac

  printf "Deploying PiWatcher base to %s:%s\n" \
    "${remote}" \
    "${project_dir}"

  open_ssh_master "${remote}" "${control_path}"

  local service_enabled_before
  service_enabled_before="$(ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "if sudo systemctl is-enabled --quiet piwatcher-base.service; then echo true; else echo false; fi")"
  local service_active_before
  service_active_before="$(ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "if sudo systemctl is-active --quiet piwatcher-base.service; then echo true; else echo false; fi")"

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

  if [[ -f "${base_env_file}" ]]; then
    scp "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" \
      "${base_env_file}" \
      "${remote}:${project_dir}/.env"
    printf "Copied %s to %s:%s/.env\n" \
      "${base_env_file}" \
      "${remote}" \
      "${project_dir}"
  else
    printf "No base env file found at %s; keeping remote .env.\n" \
      "${base_env_file}"
  fi

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "sudo install -d -o '${base_user}' -g '${base_user}' '${frame_storage_path}'"

  if [[ "${service_active_before}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl stop piwatcher-base.service"
  fi

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "test -x '${uv_bin}' && cd '${project_dir}' && docker compose up -d postgres && cd packages/base && PGOPTIONS='-c lock_timeout=10s -c statement_timeout=15min' '${uv_bin}' run alembic upgrade head"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "sudo cp '${project_dir}/deploy/piwatcher-base.service' /etc/systemd/system/piwatcher-base.service && sudo systemctl daemon-reload"

  if [[ "${enable_base_service}" == "preserve" ]]; then
    enable_base_service="${service_enabled_before}"
  fi

  if [[ "${enable_base_service}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl enable piwatcher-base.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl disable piwatcher-base.service >/dev/null 2>&1 || true"
  fi

  if [[ "${start_base}" == "preserve" ]]; then
    start_base="${service_active_before}"
  fi

  if [[ "${start_base}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl restart piwatcher-base.service && sudo systemctl status --no-pager -l piwatcher-base.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl stop piwatcher-base.service >/dev/null 2>&1 || true"
    printf "Base service is deployed but not started. Use START_BASE=true to start it.\n"
  fi
}

main "$@"
