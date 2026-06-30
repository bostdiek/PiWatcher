#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# setup-camera.sh
# First-time setup for a PiWatcher Pi Zero camera node.

set -euo pipefail

readonly SERVICE_NAME="piwatcher-camera.service"
readonly FRAME_QUEUE_DIR="/tmp/piwatcher/frames"
readonly BOOT_CONFIG="/boot/config.txt"
readonly FIRMWARE_CONFIG="/boot/firmware/config.txt"
readonly PIWATCHER_USER="${PIWATCHER_USER:-${SUDO_USER:-pi}}"
readonly PIWATCHER_HOME="${PIWATCHER_HOME:-/home/${PIWATCHER_USER}}"
readonly PROJECT_DIR="${PIWATCHER_HOME}/piwatcher"
readonly ENABLE_CAMERA_SERVICE="${ENABLE_CAMERA_SERVICE:-preserve}"

err() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

install_packages() {
  apt-get update
  apt-get install -y --no-install-recommends \
    python3-dotenv \
    python3-numpy \
    python3-picamera2 \
    python3-requests \
    python3-smbus \
    rfkill
}

configure_rfkill_sudoers() {
  local sudoers_file="/etc/sudoers.d/piwatcher-rfkill"

  printf "%s ALL=(root) NOPASSWD: /usr/sbin/rfkill\n" \
    "${PIWATCHER_USER}" >"${sudoers_file}"
  chmod 0440 "${sudoers_file}"
}

enable_i2c() {
  local config_file=""

  if [[ -f "${FIRMWARE_CONFIG}" ]]; then
    config_file="${FIRMWARE_CONFIG}"
  elif [[ -f "${BOOT_CONFIG}" ]]; then
    config_file="${BOOT_CONFIG}"
  else
    err "Raspberry Pi boot config not found"
  fi

  if ! grep -Eq "^dtparam=i2c_arm=on" "${config_file}"; then
    printf "\ndtparam=i2c_arm=on\n" >>"${config_file}"
  fi
}

install_service() {
  local source_service="${PROJECT_DIR}/deploy/${SERVICE_NAME}"

  if [[ ! -f "${source_service}" ]]; then
    err "Service file not found at ${source_service}"
  fi

  sed \
    -e "s|^User=.*|User=${PIWATCHER_USER}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${PROJECT_DIR}|" \
    "${source_service}" >"/etc/systemd/system/${SERVICE_NAME}"
  systemctl daemon-reload
  case "${ENABLE_CAMERA_SERVICE}" in
    true)
      systemctl enable "${SERVICE_NAME}"
      ;;
    false)
      systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
      ;;
    preserve|"")
      ;;
    *)
      err "ENABLE_CAMERA_SERVICE must be true, false, or preserve"
      ;;
  esac
}

main() {
  if (( EUID != 0 )); then
    err "Run this script with sudo"
  fi

  install_packages
  configure_rfkill_sudoers
  enable_i2c
  mkdir -p "${FRAME_QUEUE_DIR}"
  chown -R "${PIWATCHER_USER}:${PIWATCHER_USER}" /tmp/piwatcher
  chown -R "${PIWATCHER_USER}:${PIWATCHER_USER}" "${PROJECT_DIR}"
  install_service
  printf "PiWatcher camera setup complete. Create %s/.env, then start %s.\n" \
    "${PROJECT_DIR}" \
    "${SERVICE_NAME}"
}

main "$@"
