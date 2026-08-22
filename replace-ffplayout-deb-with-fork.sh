#!/usr/bin/env bash
#
# Replace the .deb-installed ffplayout with a build from the fork at
# ~/src/ffplayout. Steps mirror ~/ffplayout-deb-to-fork-install.txt.
#
# Usage: ./replace-ffplayout-deb-with-fork.sh
#
# Preserves: /usr/share/ffplayout (db + web assets), /var/lib/ffplayout
# (playlists + media), the ffpu user, and any systemd drop-in override.
# Backs up: old binary, old unit file, old override.d, db tarball -> in
# ~/ffplayout-deb-backup/

set -euo pipefail

REPO_DIR="${FFPLAYOUT_REPO_DIR:-$HOME/src/ffplayout}"
BACKUP_DIR="$HOME/ffplayout-deb-backup"
SERVICE_NAME="ffplayout"
BIN_PATH="/usr/bin/ffplayout"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_DIR="/var/log/${SERVICE_NAME}"
SERVICE_USER="ffpu"
LISTEN_ADDR="${FFPLAYOUT_LISTEN:-0.0.0.0:8787}"

log() { printf '\n==> %s\n' "$1"; }
die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] && die "Run as your normal user, not root (script uses sudo where needed)."

command -v sudo >/dev/null || die "sudo not found."

log "Checking existing install"
if ! dpkg -l ffplayout >/dev/null 2>&1; then
    die "ffplayout is not installed via apt/dpkg - nothing to replace. Aborting."
fi
dpkg -l ffplayout

if [[ ! -f /usr/lib/systemd/system/${SERVICE_NAME}.service ]]; then
    die "Expected /usr/lib/systemd/system/${SERVICE_NAME}.service (dpkg-owned unit) not found."
fi

[[ -d "$REPO_DIR" ]] || die "Fork repo not found at $REPO_DIR (set FFPLAYOUT_REPO_DIR to override)."

# --- 1. Back up ------------------------------------------------------------
log "Backing up current binary, unit file, override.d, and database"
mkdir -p "$BACKUP_DIR"
sudo cp "$BIN_PATH" "$BACKUP_DIR/ffplayout.old"
sudo cp "/usr/lib/systemd/system/${SERVICE_NAME}.service" "$BACKUP_DIR/ffplayout.service.orig"
if [[ -d "/etc/systemd/system/${SERVICE_NAME}.service.d" ]]; then
    sudo cp -r "/etc/systemd/system/${SERVICE_NAME}.service.d" "$BACKUP_DIR/"
fi
if [[ -d /usr/share/ffplayout/db ]]; then
    sudo tar czf "$BACKUP_DIR/db-backup.tar.gz" -C /usr/share/ffplayout db
fi
sudo chown -R "$(whoami)": "$BACKUP_DIR"
echo "Backup written to $BACKUP_DIR"

# --- 2. Build ----------------------------------------------------------------
log "Building release binary from $REPO_DIR"
( cd "$REPO_DIR" && cargo build --release -p ffplayout )
NEW_BIN="$REPO_DIR/target/release/ffplayout"
[[ -x "$NEW_BIN" ]] || die "Build finished but $NEW_BIN not found/executable."

# --- 3. Stop -------------------------------------------------------------
log "Stopping running service"
sudo systemctl stop "$SERVICE_NAME" || true

# --- 4. Remove package (not purge) ----------------------------------------
log "Removing ffplayout package (apt remove, NOT purge)"
sudo apt-get remove -y ffplayout

# --- 5. Install new binary -------------------------------------------------
log "Installing new binary to $BIN_PATH"
sudo cp "$NEW_BIN" "$BIN_PATH"
sudo chown root:root "$BIN_PATH"
sudo chmod 755 "$BIN_PATH"

# --- 6. Unmask service -----------------------------------------------------
log "Unmasking service (apt remove masks it via /dev/null symlink)"
sudo systemctl unmask "$SERVICE_NAME"

# --- 7. Recreate systemd unit -----------------------------------------------
log "Writing systemd unit to $UNIT_PATH"
sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=Rust and ffmpeg based playout solution
After=network.target remote-fs.target

[Service]
ExecStart=${BIN_PATH} -l ${LISTEN_ADDR}
Restart=always
StartLimitInterval=20
RestartSec=1
KillMode=mixed
User=${SERVICE_USER}

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload

# --- 8. Recreate log directory ----------------------------------------------
log "Recreating log directory $LOG_DIR"
sudo mkdir -p "$LOG_DIR"
sudo chown "${SERVICE_USER}:" "$LOG_DIR"

# --- 9. Start and verify -----------------------------------------------------
log "Starting service"
sudo systemctl enable --now "$SERVICE_NAME"
sleep 2
systemctl status "$SERVICE_NAME" --no-pager || true
"$BIN_PATH" -V

log "Done. Rollback material is in $BACKUP_DIR if needed."
