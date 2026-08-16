# jukebox

Play music through Spotify by scanning RFID tags on a Raspberry Pi.

Inspired by [A Modern Day Record Player](https://talaexe.com/moderndayrecordplayer) by @talaexe.

## Repository layout

```
jukebox/
├── jukebox.py           # Entry point (CLI + RFID loop)
├── spotify_auth.py      # OAuth, token refresh, invalid_grant recovery
├── logger.py            # File logging to /var/log/jukebox/scan.log
├── rfid_mapping.py      # RFID UID → Spotify URI map
├── requirements.txt     # Python dependencies
├── .env.example         # Spotify API credentials template
├── scripts/
│   └── setup_venv.sh    # Create venv and install deps (run once)
└── deploy/
    ├── jukebox.service  # systemd unit file    
    └── install.sh       # Copy app + enable service on the Pi
```

## Raspberry Pi setup

1. Clone or copy this repo to the Pi (default install path: `/home/jukebox/spotify`).
2. Create credentials:
   ```bash
   cp .env.example .env
   # edit .env with your Spotify app credentials
   ```
   In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), open your app → Settings → Redirect URIs and add:
   ```
   http://127.0.0.1:8888/callback
   ```
   Remove any `localhost` URIs — Spotify no longer accepts them. The URI in `.env` must match exactly.
3. Install the virtualenv (once):
   ```bash
   bash scripts/setup_venv.sh
   ```
4. Authorize Spotify (once, on the Pi or another machine with the same `.cache` path):
   ```bash
   source .venv/bin/activate
   python jukebox.py --reauth
   ```
   1. Open the printed URL in a browser and approve access.
   2. After approving, your browser redirects to `http://127.0.0.1:8888/callback?code=...` — the page may fail to load; that is expected.
   3. Copy the **full URL from your browser's address bar** (not the sign-in URL) and paste it into the terminal.

   A `.cache` file is written in the project directory. Access tokens refresh automatically. If Spotify returns `invalid_grant`, discard happens automatically — run `--reauth` again.
5. Install and enable the systemd service:
   ```bash
   sudo bash deploy/install.sh
   sudo systemctl start jukebox
   ```

## Manual RFID mode

```bash
source .venv/bin/activate
python jukebox.py --rfid
```

## Re-authenticate Spotify

When your refresh token expires (Spotify invalidates them after extended inactivity), run:

```bash
source .venv/bin/activate
python jukebox.py --reauth
```

## Logs

RFID scans and playback events are written to `/var/log/jukebox/scan.log` with timestamps. Follow them with:

```bash
tail -f /var/log/jukebox/scan.log
```

Example lines:

```
2026-08-16 12:05:01 INFO Jukebox is ready. Tap a card to play music.
2026-08-16 12:05:14 INFO Scanned RFID UID: 642352926973
2026-08-16 12:05:14 INFO Mapped UID 642352926973 to track: spotify:track:4RVbK6cV0VqWdpCDcx3hiT
2026-08-16 12:05:15 INFO Playing track: spotify:track:4RVbK6cV0VqWdpCDcx3hiT
```

The log rotates automatically at 5 MB (keeps 5 backups). Override the directory with `JUKEBOX_LOG_DIR` in `.env` or the systemd service.

If `/var/log/jukebox` is not writable, logs fall back to `logs/scan.log` in the project directory.

## Troubleshooting startup

```bash
systemctl status jukebox
journalctl -u jukebox -b --no-pager
```

Common issues:

- **Repeating log lines with no error** — the service is crash-looping before errors were flushed to disk. Pull the latest code; failures now log `Jukebox service failed to start:` with a full traceback in `scan.log`. Also confirm `.cache` exists after reinstall.
- **redirect_uri issues** — `SPOTIPY_REDIRECT_URI` must match your Spotify app settings exactly (including `http` vs `https` and trailing slash). Do not use `localhost`; use `127.0.0.1`.
- **Invalid authorization code** — you pasted the sign-in URL instead of the redirect URL. Paste the URL from your browser after approving access (`http://127.0.0.1:8888/callback?code=...`).
- **Service exits immediately** — the service must pass `--rfid`. Without it the script prints a usage message and exits.
- **Spotify auth fails** — ensure `.env` exists and `.cache` is present. If the refresh token expired, run `python jukebox.py --reauth`.
- **AUTH ERROR in logs** — your tag is likely an NTAG sticker, not MIFARE Classic. The jukebox only needs the tag UID, so it uses `read_id()` instead of `read()` to skip card authentication. Pull the latest code and restart the service.
- **Tag not recognized** — check `journalctl -u jukebox -f` for the scanned UID and add that exact number to `rfid_mapping.py` (do not guess from what's printed on the sticker).
- **RFID reader not found** — the `jukebox` user needs access to SPI/GPIO (`spi`, `gpio` groups on Raspberry Pi OS).
- **No playback device** — open Spotify on a phone or speaker once so an active device is available.

## CLI examples

```bash
python jukebox.py --song "Song Name" --artist "Artist" --play
python jukebox.py --track 4RVbK6cV0VqWdpCDcx3hiT --play
python jukebox.py --playlist 4Oyvo936CnKDtdLQiPfIOV --play --random
```
