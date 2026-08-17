#!/usr/bin/env bash
# Install the jukebox systemd service on linux.
# Usage: sudo ./deploy/install.sh [install_dir] [service_user]
set -euo pipefail

INSTALL_DIR="${1:-/home/jukebox/spotify}"
SERVICE_USER="${2:-jukebox}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_FILE="/etc/systemd/system/jukebox.service"

function prechecks {
  if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0"
    exit 1
  fi

  if ! id "$SERVICE_USER" &>/dev/null; then
    echo "User $SERVICE_USER does not exist."
    exit 1
  fi
}

function install {
  echo "Copying files to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"
  rsync -a --exclude '.git' --exclude '.venv' "$REPO_ROOT/" "$INSTALL_DIR/"

  if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    echo "Create $INSTALL_DIR/.env from .env.example before starting the service."
  fi
  echo "Setting up python virtual environment..."
  bash "$INSTALL_DIR/scripts/setup_venv.sh"
}

function log_setup {
  echo "Setting up log directory..."
  LOG_DIR="/var/log/jukebox"
  mkdir -p "$LOG_DIR"
  chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
  chmod 755 "$LOG_DIR"
  echo "Logs are available at /var/log/jukebox/"
}

function service_setup {
  sed \
    -e "s|/home/jukebox/spotify|$INSTALL_DIR|g" \
    -e "s|User=jukebox|User=$SERVICE_USER|g" \
    -e "s|Group=jukebox|Group=$SERVICE_USER|g" \
    "$SCRIPT_DIR/jukebox.service" > "$SERVICE_FILE"

  systemctl daemon-reload
  systemctl enable jukebox.service
}

function success {
  echo "Installed. Start with: systemctl start jukebox"
  echo "Logs: tail -f /var/log/jukebox/scan.log"
  echo "      journalctl -u jukebox -f"
}

prechecks && install && log_setup && service_setup

if [ $? -eq 0 ]; then
  success
else
  echo "Something failed during installation. Please review, resolve, then re-run the script."
fi
