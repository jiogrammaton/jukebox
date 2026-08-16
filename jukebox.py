import argparse
import random
import re
import sys
from pathlib import Path
from time import sleep

from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO
from spotipy.exceptions import SpotifyException

from logger import flush_logs, setup_logging
from rfid_mapping import RFID_MAPPING
from spotify_auth import REAUTH_COMMAND, create_session

APP_DIR = Path(__file__).resolve().parent
log = setup_logging()
SPOTIFY_URI_RE = re.compile(
    r"^spotify:(?P<kind>track|playlist|album|artist):(?P<id>[A-Za-z0-9]+)$"
)
OPEN_SPOTIFY_RE = re.compile(
    r"https?://open\.spotify\.com/(?P<kind>track|playlist|album|artist)/(?P<id>[A-Za-z0-9]+)"
)

parser = argparse.ArgumentParser(description="Spotify jukebox controlled by RFID tags")
parser.add_argument("--song", "-s", help="The name of the song")
parser.add_argument("--artist", "-a", help="The name of the artist")
parser.add_argument("--playlist", "-l", help="The name of the playlist")
parser.add_argument("--track", "-t", help="Spotify track ID or URI to play")
parser.add_argument("--play", "-p", action="store_true", help="Play track or playlist")
parser.add_argument("--random", "-r", action="store_true", help="Randomize/shuffle tracks")
parser.add_argument("--rfid", action="store_true", help="Enable RFID mode for scanning cards")
parser.add_argument(
    "--reauth",
    action="store_true",
    help="Discard the stored token and sign in to Spotify again",
)
args = parser.parse_args()

_session = None


def get_session():
    global _session
    if _session is None:
        _session = create_session(
            APP_DIR,
            force_reauth=args.reauth,
            interactive=None if not args.reauth else True,
        )
    return _session


def normalize_spotify_uri(value: str) -> str:
    value = value.strip()
    if value.startswith("spotify:"):
        return value

    match = OPEN_SPOTIFY_RE.match(value)
    if match:
        kind = match.group("kind")
        track_id = match.group("id")
        return f"spotify:{kind}:{track_id}"

    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return f"spotify:track:{value}"

    raise ValueError(
        f"Invalid Spotify URI or ID: {value}. "
        "Use spotify:track:..., a track ID, or an open.spotify.com URL."
    )


def uri_kind(uri: str) -> str:
    match = SPOTIFY_URI_RE.match(uri)
    if match:
        return match.group("kind")

    raise ValueError(f"Unsupported Spotify URI format: {uri}")


def get_active_device_id():
    devices = get_session().call(lambda sp: sp.devices())
    if not devices["devices"]:
        return None

    for device in devices["devices"]:
        if device.get("is_active"):
            return device["id"]

    return devices["devices"][0]["id"]


def display_track_info(track):
    if not args.play:
        print(f"{track['name']} by {track['artists'][0]['name']}")
        print(f"   Album Cover: {track['album']['images'][0]['url']}")
        print(f"   Album: {track['album']['name']}")
        print(f"   Spotify Link: {track['external_urls']['spotify']}")
        print("-" * 50)


def check_active_device():
    device_id = get_active_device_id()
    if not device_id:
        log.warning(
            "No active device found. Open Spotify on a phone, desktop, "
            "or speaker and start playback once so it becomes available."
        )
        return False
    return True


def play_song(track_uri):
    track_uri = normalize_spotify_uri(track_uri)
    if uri_kind(track_uri) != "track":
        raise ValueError(f"Expected a track URI, got: {track_uri}")

    device_id = get_active_device_id()
    if not device_id:
        log.warning(
            "No active device found. Open Spotify on a phone, desktop, "
            "or speaker and start playback once so it becomes available."
        )
        return

    track_id = track_uri.rsplit(":", maxsplit=1)[-1]

    try:
        get_session().call(
            lambda sp: sp.start_playback(
                uris=[track_uri],
                device_id=device_id,
            )
        )
        log.info("Playing track: %s", track_uri)
        return
    except SpotifyException as exc:
        log.warning("Direct track playback failed: %s", exc)

    try:
        track = get_session().call(lambda sp: sp.track(track_id))
        album_uri = track["album"]["uri"]
        get_session().call(
            lambda sp: sp.start_playback(
                context_uri=album_uri,
                offset={"uri": track_uri},
                device_id=device_id,
            )
        )
        log.info(
            "Playing track via album context: %s by %s",
            track["name"],
            track["artists"][0]["name"],
        )
    except SpotifyException as exc:
        log.error("Failed to play track %s: %s", track_uri, exc)


def play_album(album_uri):
    if not check_active_device():
        return

    album_id = album_uri.rsplit(":", maxsplit=1)[-1]
    album = get_session().call(lambda sp: sp.album(album_id))
    get_session().call(lambda sp: sp.shuffle(state=False))

    if args.random:
        tracks = get_session().call(lambda sp: sp.album_tracks(album_id))
        track_uris = [item["uri"] for item in tracks["items"]]
        get_session().call(lambda sp: sp.shuffle(state=True))
        log.info("Shuffle mode enabled.")
        random_track_uri = random.choice(track_uris)
        log.info("Random track selected: %s", random_track_uri)
        get_session().call(
            lambda sp: sp.start_playback(
                context_uri=album_uri,
                offset={"uri": random_track_uri},
            )
        )
        log.info(
            "Playing album: %s (%s) starting from a random track",
            album["name"],
            album_uri,
        )
    else:
        get_session().call(lambda sp: sp.start_playback(context_uri=album_uri))
        log.info("Playing album: %s (%s) from the first track", album["name"], album_uri)


def play_playlist(playlist_uri):
    if check_active_device():
        playlist_tracks = get_session().call(lambda sp: sp.playlist_tracks(playlist_uri))
        track_uris = [item["track"]["uri"] for item in playlist_tracks["items"]]
        get_session().call(lambda sp: sp.shuffle(state=False))

        if args.random:
            get_session().call(lambda sp: sp.shuffle(state=True))
            log.info("Shuffle mode enabled.")
            random_track_uri = random.choice(track_uris)
            log.info("Random track selected: %s", random_track_uri)
            get_session().call(lambda sp: sp.start_playback(context_uri=playlist_uri))
            log.info("Playing playlist: %s starting from a random track", playlist_uri)
        else:
            log.info("Shuffle mode disabled.")
            get_session().call(lambda sp: sp.start_playback(context_uri=playlist_uri))
            log.info("Playing playlist: %s starting from the first track", playlist_uri)


def enable_shuffle():
    if check_active_device():
        get_session().call(lambda sp: sp.shuffle(state=True))
        print("Shuffle mode enabled for subsequent tracks.")


def search_song(song, artist):
    query = f"track:{song} artist:{artist}"
    results = get_session().call(lambda sp: sp.search(q=query, limit=1))

    if results["tracks"]["items"]:
        track = results["tracks"]["items"][0]
        print(f"Displaying track info: {track['name']} by {track['artists'][0]['name']}")
        display_track_info(track)

        if args.play:
            play_song(track["uri"])
    else:
        print("No results found for your search.")


def search_playlist(playlist_name_or_id):
    try:
        print(f"Attempting to fetch playlist by ID: {playlist_name_or_id}")
        playlist = get_session().call(lambda sp: sp.playlist(playlist_name_or_id))

        if not args.play:
            print(f"Displaying tracks for playlist: {playlist['name']}")
            display_playlist_tracks(playlist["id"])
        if args.play:
            play_playlist(playlist["uri"])
    except Exception as e:
        print(f"Error fetching playlist by ID: {e}")
        print(f"Attempting to search for playlist by name: {playlist_name_or_id}")

        playlists = get_session().call(lambda sp: sp.current_user_playlists())
        matched_playlists = [
            playlist
            for playlist in playlists["items"]
            if playlist_name_or_id.lower() in playlist["name"].lower()
        ]

        if matched_playlists:
            playlist_id = matched_playlists[0]["id"]
            if not args.play:
                print(f"Displaying tracks for playlist: {matched_playlists[0]['name']}")
                display_playlist_tracks(playlist_id)
            if args.play:
                play_playlist(matched_playlists[0]["uri"])
        else:
            print(f"No playlists found with the name or ID '{playlist_name_or_id}' in your library.")


def display_playlist_tracks(playlist_id):
    results = get_session().call(lambda sp: sp.playlist_tracks(playlist_id))

    for idx, item in enumerate(results["items"]):
        track = item["track"]
        print(f"{idx + 1}. ", end="")
        display_track_info(track)


def fail_service(message: str, exc: BaseException | None = None) -> None:
    if exc is not None:
        log.exception(message)
    else:
        log.error(message)
    flush_logs()
    sys.exit(1)


def run_rfid_loop():
    reader = SimpleMFRC522()

    log.info("Jukebox is ready. Tap a card to play music.")

    try:
        while True:
            log.debug("Waiting for RFID scan...")
            scanned_id = reader.read_id()
            log.info("Scanned RFID UID: %s", scanned_id)

            uri = RFID_MAPPING.get(scanned_id)
            if uri:
                try:
                    normalized_uri = normalize_spotify_uri(uri)
                    kind = uri_kind(normalized_uri)
                    log.info("Mapped UID %s to %s: %s", scanned_id, kind, normalized_uri)
                    if kind == "track":
                        play_song(normalized_uri)
                    elif kind == "playlist":
                        play_playlist(normalized_uri)
                    elif kind == "album":
                        play_album(normalized_uri)
                    else:
                        log.error(
                            "Unsupported mapped URI type '%s': %s",
                            kind,
                            normalized_uri,
                        )
                except (RuntimeError, ValueError) as exc:
                    log.error("%s", exc)
                    if isinstance(exc, RuntimeError):
                        log.error("Playback paused until you run: %s", REAUTH_COMMAND)
                except SpotifyException as exc:
                    log.error("Spotify playback failed: %s", exc)
            else:
                log.warning("No mapping found for RFID UID: %s", scanned_id)

            sleep(1)
    except KeyboardInterrupt:
        log.info("Exiting RFID jukebox.")
    except Exception as e:
        fail_service(f"RFID loop crashed: {e}", e)
    finally:
        GPIO.cleanup()


def main() -> None:
    mode = "rfid" if args.rfid else "cli"
    log.info("Jukebox service starting (mode=%s)", mode)

    try:
        if args.reauth:
            get_session()
            log.info("Spotify re-authentication complete.")
        elif args.rfid:
            get_session()
            run_rfid_loop()
        elif args.song and args.artist:
            get_session()
            search_song(args.song, args.artist)
        elif args.track:
            get_session()
            if args.play:
                play_song(args.track)
            else:
                track_uri = normalize_spotify_uri(args.track)
                track = get_session().call(
                    lambda sp: sp.track(track_uri.rsplit(":", maxsplit=1)[-1])
                )
                display_track_info(track)
        elif args.playlist:
            get_session()
            if args.random:
                enable_shuffle()
            search_playlist(args.playlist)
        else:
            print("Provide --rfid, --reauth, --track, or --song/--artist, or --playlist.")
    except Exception as exc:
        fail_service(f"Jukebox service failed to start: {exc}", exc)


if __name__ == "__main__":
    main()
