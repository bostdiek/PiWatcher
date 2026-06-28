#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# deploy-inference.sh
# Deploy PiWatcher host inference files to a Pi 5 and install the systemd unit.

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_ENV="${REPO_ROOT}/.env"
readonly SETUP_SRC="${REPO_ROOT}/deploy/setup-llama-swap.sh"
readonly SERVICE_SRC="${REPO_ROOT}/deploy/piwatcher-inference.service"
readonly DEFAULT_MODELS_DIR="/home/bostdiek/piwatcher/models"

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
Usage: deploy/deploy-inference.sh <pi5-host> [pi5-user]

Environment overrides:
  BASE_PROJECT_DIR          Remote repo path. Defaults to /home/<user>/Projects/PiWatcher
  LLAMA_SWAP_MODELS_DIR     Model directory to create/chown before setup
  ENABLE_INFERENCE_SERVICE  Defaults to false
  START_INFERENCE           Defaults to false
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

  if [[ ! -f "${ROOT_ENV}" ]]; then
    return
  fi

  awk -F= -v key="${key}" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "${ROOT_ENV}"
}

setting_value() {
  local name="$1"
  local default="$2"
  local value="${!name:-}"

  if [[ -z "${value}" ]]; then
    value="$(read_env_value "${name}")"
  fi

  printf "%s" "${value:-${default}}"
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

  [[ -f "${SETUP_SRC}" ]] || err "Setup script not found at ${SETUP_SRC}"
  [[ -f "${SERVICE_SRC}" ]] || err "Service file not found at ${SERVICE_SRC}"

  local remote="${base_user}@${base_host}"
  local project_dir="${BASE_PROJECT_DIR:-/home/${base_user}/Projects/PiWatcher}"
  local models_dir
  models_dir="$(setting_value LLAMA_SWAP_MODELS_DIR "${DEFAULT_MODELS_DIR}")"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local control_path="${tmp_dir}/ssh-control"
  cleanup_remote="${remote}"
  cleanup_control_path="${control_path}"
  cleanup_tmp_dir="${tmp_dir}"
  trap cleanup EXIT

  printf "Deploying PiWatcher inference to %s:%s\n" \
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
    "sudo install -d -o '${base_user}' -g '${base_user}' '${models_dir}'"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "cd '${project_dir}' && LLAMA_SWAP_RUNTIME=host bash deploy/setup-llama-swap.sh"

  ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
    "sudo cp '${project_dir}/deploy/piwatcher-inference.service' /etc/systemd/system/piwatcher-inference.service && sudo systemctl daemon-reload"

  if [[ "${ENABLE_INFERENCE_SERVICE:-false}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl enable piwatcher-inference.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl disable piwatcher-inference.service >/dev/null 2>&1 || true"
  fi

  if [[ "${START_INFERENCE:-false}" == "true" ]]; then
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl restart piwatcher-inference.service && sudo systemctl status --no-pager piwatcher-inference.service"
  else
    ssh "${SSH_OPTIONS[@]}" -o ControlPath="${control_path}" "${remote}" \
      "sudo systemctl stop piwatcher-inference.service >/dev/null 2>&1 || true"
    printf "Inference service is deployed but not started. Use START_INFERENCE=true to start it.\n"
  fi
}

main "$@"
