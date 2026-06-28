#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# setup-llama-swap.sh
# Prepare llama-swap model storage and optionally download configured models.

set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_ENV="${REPO_ROOT}/.env"
readonly CONFIG_FILE="${REPO_ROOT}/deploy/llama-swap/config.yaml"
readonly DEFAULT_LLAMA_SWAP_BIN="/home/bostdiek/.local/bin/llama-swap"
readonly DEFAULT_LLAMA_SERVER_BIN="/home/bostdiek/Projects/llama.cpp/build/bin/llama-server"
readonly DEFAULT_LLAMA_SWAP_LISTEN="127.0.0.1:8080"
readonly DEFAULT_LLAMA_SWAP_MODEL="lfm2.5-vl-450m-q4_0"
readonly DEFAULT_LLAMA_SWAP_MODELS_DIR="/home/bostdiek/piwatcher/models"
readonly DEFAULT_LLAMA_SWAP_MODEL_FILE="LFM2.5-VL-450M-Q4_0.gguf"
readonly DEFAULT_LLAMA_SWAP_MEDIA_PATH="/home/bostdiek/Downloads"

err() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
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

download_if_missing() {
  local url="$1"
  local destination="$2"
  local label="$3"

  if [[ -z "${url}" ]]; then
    return
  fi

  if [[ -f "${destination}" ]]; then
    printf "%s file exists: %s\n" "${label}" "${destination}"
    return
  fi

  local partial_destination="${destination}.part"

  mkdir -p "$(dirname "${destination}")"
  printf "Downloading %s to %s\n" "${label}" "${destination}"
  curl -fL --continue-at - -o "${partial_destination}" "${url}"
  mv "${partial_destination}" "${destination}"
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

write_config() {
  local model_id="$1"
  local llama_server_bin="$2"
  local model_path="$3"
  local mmproj_path="$4"
  local media_path="$5"
  local runtime="$6"

  mkdir -p "$(dirname "${CONFIG_FILE}")"

  if [[ "${runtime}" == "docker" ]]; then
    local model_file
    local mmproj_file
    local mmproj_arg=""

    model_file="$(basename "${model_path}")"

    if [[ -n "${mmproj_path}" ]]; then
      mmproj_file="$(basename "${mmproj_path}")"
      mmproj_arg=" --mmproj /models/${mmproj_file}"
    fi

    cat >"${CONFIG_FILE}" <<EOF
models:
  ${model_id}:
    cmd: llama-server --host 127.0.0.1 --port \${PORT} --model /models/${model_file}${mmproj_arg}
    ttl: 300
EOF
    return
  fi

  cat >"${CONFIG_FILE}" <<EOF
models:
  ${model_id}:
    cmd: |
      ${llama_server_bin}
      --model ${model_path}
      --host 127.0.0.1
      --port \${PORT}
      --ctx-size 1000
      --cache-ram 512
      --media-path ${media_path}
EOF

  if [[ -n "${mmproj_path}" ]]; then
    cat >>"${CONFIG_FILE}" <<EOF
      --mmproj ${mmproj_path}
EOF
  fi

  cat >>"${CONFIG_FILE}" <<EOF
    ttl: 300
EOF
}

manual_placement_message() {
  local label="$1"
  local destination="$2"
  local url_variable="$3"

  printf "%s file missing: %s\n" "${label}" "${destination}" >&2
  printf "Place the file manually, for example:\n" >&2
  printf "  mkdir -p %q\n" "$(dirname "${destination}")" >&2
  printf "  cp /path/to/%s %q\n" "$(basename "${destination}")" "${destination}" >&2
  printf "Or set %s in .env and rerun this script.\n" "${url_variable}" >&2
}

validate_executable() {
  local description="$1"
  local path="$2"

  if [[ ! -x "${path}" ]]; then
    err "${description} must be executable: ${path}"
  fi
}

main() {
  if ! command -v curl >/dev/null 2>&1; then
    err "curl is required"
  fi

  local models_dir
  local model_id
  local model_file
  local mmproj_file
  local model_url
  local mmproj_url
  local llama_swap_bin
  local llama_server_bin
  local listen_address
  local media_path
  local runtime

  llama_swap_bin="$(setting_value LLAMA_SWAP_BIN "${DEFAULT_LLAMA_SWAP_BIN}")"
  llama_server_bin="$(setting_value LLAMA_SERVER_BIN "${DEFAULT_LLAMA_SERVER_BIN}")"
  listen_address="$(setting_value LLAMA_SWAP_LISTEN "${DEFAULT_LLAMA_SWAP_LISTEN}")"
  models_dir="$(setting_value LLAMA_SWAP_MODELS_DIR "${DEFAULT_LLAMA_SWAP_MODELS_DIR}")"
  model_id="$(setting_value LLAMA_SWAP_MODEL "${DEFAULT_LLAMA_SWAP_MODEL}")"
  model_file="$(setting_value LLAMA_SWAP_MODEL_FILE "${DEFAULT_LLAMA_SWAP_MODEL_FILE}")"
  mmproj_file="$(setting_value LLAMA_SWAP_MMPROJ_FILE "")"
  model_url="$(setting_value LLAMA_SWAP_MODEL_URL "")"
  mmproj_url="$(setting_value LLAMA_SWAP_MMPROJ_URL "")"
  media_path="$(setting_value LLAMA_SWAP_MEDIA_PATH "${DEFAULT_LLAMA_SWAP_MEDIA_PATH}")"
  runtime="$(setting_value LLAMA_SWAP_RUNTIME "host")"

  local model_path="${models_dir}/${model_file}"
  local mmproj_path=""

  if [[ -n "${mmproj_file}" ]]; then
    mmproj_path="${models_dir}/${mmproj_file}"
  fi

  if [[ "${runtime}" == "host" ]]; then
    validate_executable "LLAMA_SERVER_BIN" "${llama_server_bin}"
    validate_executable "LLAMA_SWAP_BIN" "${llama_swap_bin}"
  elif [[ "${runtime}" != "docker" ]]; then
    err "LLAMA_SWAP_RUNTIME must be 'host' or 'docker': ${runtime}"
  fi

  mkdir -p "${models_dir}"
  download_if_missing "${model_url}" "${model_path}" "Model"

  if [[ -n "${mmproj_path}" ]]; then
    download_if_missing "${mmproj_url}" "${mmproj_path}" "Multimodal projector"
  fi

  if [[ ! -f "${model_path}" ]]; then
    manual_placement_message "Model" "${model_path}" "LLAMA_SWAP_MODEL_URL"
    err "model file is required for llama-swap setup"
  fi

  if [[ -n "${mmproj_path}" && ! -f "${mmproj_path}" ]]; then
    manual_placement_message \
      "Multimodal projector" \
      "${mmproj_path}" \
      "LLAMA_SWAP_MMPROJ_URL"
    err "multimodal projector file is required when LLAMA_SWAP_MMPROJ_FILE is set"
  fi

  write_config \
    "${model_id}" \
    "${llama_server_bin}" \
    "${model_path}" \
    "${mmproj_path}" \
    "${media_path}" \
    "${runtime}"

  printf "Wrote llama-swap config: %s\n" "${CONFIG_FILE}"

  if [[ "${runtime}" == "host" ]]; then
    printf "Start host llama-swap with:\n"
    printf "  %q --config %q --listen %q\n" \
      "${llama_swap_bin}" \
      "${CONFIG_FILE}" \
      "${listen_address}"
  fi
}

main "$@"
