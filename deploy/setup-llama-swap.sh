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

  if [[ -z "${url}" ]]; then
    return
  fi

  if [[ -f "${destination}" ]]; then
    printf "Model file exists: %s\n" "${destination}"
    return
  fi

  printf "Downloading %s\n" "${destination}"
  curl -fL --create-dirs -o "${destination}" "${url}"
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
  local model_file="$2"
  local mmproj_file="$3"

  mkdir -p "$(dirname "${CONFIG_FILE}")"
  cat >"${CONFIG_FILE}" <<EOF
models:
  ${model_id}:
    cmd: llama-server --host 127.0.0.1 --port \${PORT} --model /models/${model_file} --mmproj /models/${mmproj_file}
    ttl: 300
EOF
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

  models_dir="$(setting_value LLAMA_SWAP_MODELS_DIR "${REPO_ROOT}/tmp/llama-swap/models")"
  model_id="$(setting_value LLAMA_SWAP_MODEL "lfm2-vl-450m")"
  model_file="$(setting_value LLAMA_SWAP_MODEL_FILE "lfm2-vl-450m.gguf")"
  mmproj_file="$(setting_value LLAMA_SWAP_MMPROJ_FILE "lfm2-vl-450m-mmproj.gguf")"
  model_url="$(setting_value LLAMA_SWAP_MODEL_URL "")"
  mmproj_url="$(setting_value LLAMA_SWAP_MMPROJ_URL "")"

  mkdir -p "${models_dir}"
  write_config "${model_id}" "${model_file}" "${mmproj_file}"

  download_if_missing "${model_url}" "${models_dir}/${model_file}"
  download_if_missing "${mmproj_url}" "${models_dir}/${mmproj_file}"

  if [[ ! -f "${models_dir}/${model_file}" ]]; then
    printf "Model file missing: %s\n" "${models_dir}/${model_file}"
    printf "Set LLAMA_SWAP_MODEL_URL in .env or place the file manually.\n"
  fi

  if [[ ! -f "${models_dir}/${mmproj_file}" ]]; then
    printf "Multimodal projector missing: %s\n" "${models_dir}/${mmproj_file}"
    printf "Set LLAMA_SWAP_MMPROJ_URL in .env or place the file manually.\n"
  fi
}

main "$@"