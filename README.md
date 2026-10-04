# jukebox

Play music through Spotify by scanning RFID tags on Linux.

Inspired by [A Modern Day Record Player](https://talaexe.com/moderndayrecordplayer) by @talaexe.

## Repository Layout

```
jukebox/
├── jukebox.py           # Main execution script
├── spotify_auth.py      # Token refresh and authentication 
├── logger.py            # Handles logging to /var/log/jukebox/scan.log
├── rfid_mapping.py      # RFID UID to Spotify URI map
├── requirements.txt     # Python dependencies
├── .env.example         # Spotify API credentials template
├── scripts/
│   └── setup_venv.sh    # Create venv and install deps (run once)
│   └── read.py          # Scan RFID tag for its encoded value
└── deploy/
    ├── jukebox.service  # systemd unit file    
    └── install.sh       # Copy app + enable service on the Pi
```

## Prerequisites
You must have the following products:
- RFID RC522 Module
https://amzn.to/3RWqQxf

- RFID Stickers (13.56MHz) 
https://amzn.to/4cFJyjt

- Raspberry Pi 4 
https://amzn.to/4wwIgOY

- SD card for Raspberry Pi
https://amzn.to/4wAisBB

- Female to Female Dupont Jumper Wires 
https://amzn.to/4xD80tS

> I get a small commission if you choose to purchase using the above Amazon affiliate links. 

## Setup

1. Clone or copy this repo to your Linux server (default install path: `/home/jukebox/spotify`).
2. Create mappings
   1. Copy mapping example
      ``` bash
      cp rfid_mapping.example rfid_mapping.py
   2. Activate python virtual environment
      ``` bash
      source .venv/bin/activate
      ```
   3. Launch `read.py` script
      ``` bash
      python read.py
      ```
   4. Scan RFID tag
   5. Replace column one with value
   6. Find song, album, or playlist from your spotify
   7. Copy the URI value
   8. Replace column two with your value
3. Create credentials:
   ```bash
   cp .env.example .env
   ```
   Edit .env with your Spotify app credentials
   In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), open your app → Settings → Redirect URIs and add:
   ```
   https://127.0.0.1:8888/callback
   ```
   The URI in `.env` must match exactly.
4. Authorize Spotify (once, on the Pi or another machine with the same `.cache` path):
   ```bash
   source .venv/bin/activate
   python jukebox.py --reauth
   ```
   1. Open the printed URL in a browser and approve access.
   2. After approving, your browser redirects to `https://127.0.0.1:8888/callback?code=...` (the page will fail to load; that is expected.)
   3. Copy the **full URL from your browser's address bar** and paste it into the terminal.

   A `.cache` file is written in the project directory. Access tokens refresh automatically. If Spotify returns `invalid_grant`, run `--reauth` again.
5. Run the installer:
   ```bash
   sudo bash deploy/install.sh
   ```

## Logs

RFID scans and playback events are written to `/var/log/jukebox/scan.log` with timestamps. Follow them with:

```bash
tail -f /var/log/jukebox/scan.log
```

Example log:

```
2026-08-16 12:05:01 INFO Jukebox is ready. Tap a card to play music.
2026-08-16 12:05:14 INFO Scanned RFID UID: 642352926973
2026-08-16 12:05:14 INFO Mapped UID 642352926973 to track: spotify:track:4RVbK6cV0VqWdpCDcx3hiT
2026-08-16 12:05:15 INFO Playing track: spotify:track:4RVbK6cV0VqWdpCDcx3hiT
```

The log rotates automatically at 5 MB (keeps 5 backups). Override the directory with `LOG_DIR` in `.env` or the systemd service.

If `/var/log/jukebox` is not writable, logs fall back to `logs/scan.log` in the project directory.

## Troubleshooting startup

```bash
systemctl status jukebox
journalctl -u jukebox -b --no-pager
```

Common issues:

- **redirect_uri: Insecure** — update `.env` to `http://127.0.0.1:8888/callback` and add the same URI in your Spotify app settings. Do not use `localhost` or `https://localhost`.
- **Invalid authorization code** — you pasted the sign-in URL instead of the redirect URL. Paste the URL from your browser after approving access (`http://127.0.0.1:8888/callback?code=...`).
- **Service exits immediately** — the service must pass `--rfid`. Without it the script prints a usage message and exits.
- **Spotify auth fails** — ensure `.env` exists and `.cache` is present. If the refresh token expired, run `python jukebox.py --reauth`.
- **AUTH ERROR in logs** — your tag is likely an NTAG sticker, not MIFARE Classic. The jukebox only needs the tag UID, so it uses `read_id()` instead of `read()` to skip card authentication. Pull the latest code and restart the service.
- **Tag not recognized** — check `journalctl -u jukebox -f` for the scanned UID and add that exact number to `rfid_mapping.py` (do not guess from what's printed on the sticker).
- **RFID reader not found** — the `jukebox` user needs access to SPI/GPIO (`spi`, `gpio` groups on Raspberry Pi OS).
- **No playback device** — open Spotify on a phone or speaker once so an active device is available.

## Manual CLI examples

```bash
python jukebox.py --song "Song Name" --artist "Artist" --play
python jukebox.py --track 4RVbK6cV0VqWdpCDcx3hiT --play
python jukebox.py --playlist 4Oyvo936CnKDtdLQiPfIOV --play --random
```
