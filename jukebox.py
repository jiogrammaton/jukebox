import argparse
import random
from pathlib import Path
from time import sleep

from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO

from rfid_mapping import RFID_MAPPING
from spotify_auth import REAUTH_COMMAND, create_session

APP_DIR = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description="Spotify jukebox controlled by RFID tags")
parser.add_argument("--song", "-s", help="The name of the song")
parser.add_argument("--artist", "-a", help="The name of the artist")
parser.add_argument("--playlist", "-l", help="The name of the playlist")
parser.add_argument("--play", "-p", action="store_true", help="Play track or playlist")
parser.add_argument("--random", "-r", action="store_true", help="Randomize/shuffle tracks")
parser.add_argument("--rfid", action="store_true", help="Enable RFID mode for scanning cards")
parser.add_argument(
    "--reauth",
    action="store_true",
    help="Discard the stored token and sign in to Spotify again",
)
args = parser.parse_args()

session = create_session(
    APP_DIR,
    force_reauth=args.reauth,
    interactive=None if not args.reauth else True,
)


def check_active_device():
    devices = session.call(lambda sp: sp.devices())
    if not devices["devices"]:
        print(
            "No active device found. Open Spotify on a phone, desktop, "
            "or speaker and start playback once so it becomes available."
        )
        return False
    return True


def display_track_info(track):
    if not args.play:
        print(f"{track['name']} by {track['artists'][0]['name']}")
        print(f"   Album Cover: {track['album']['images'][0]['url']}")
        print(f"   Album: {track['album']['name']}")
        print(f"   Spotify Link: {track['external_urls']['spotify']}")
        print("-" * 50)


def play_song(track_uri):
    if check_active_device():
        session.call(lambda sp: sp.start_playback(uris=[track_uri]))
        print(f"Playing: {track_uri}")


def play_playlist(playlist_uri):
    if check_active_device():
        playlist_tracks = session.call(lambda sp: sp.playlist_tracks(playlist_uri))
        track_uris = [item["track"]["uri"] for item in playlist_tracks["items"]]
        session.call(lambda sp: sp.shuffle(state=False))

        if args.random:
            session.call(lambda sp: sp.shuffle(state=True))
            print("Shuffle mode enabled.")
            random_track_uri = random.choice(track_uris)
            print(f"Random track selected: {random_track_uri}")
            session.call(lambda sp: sp.start_playback(context_uri=playlist_uri))
            print(f"Playing playlist: {playlist_uri} starting from a random track")
        else:
            print("Shuffle mode disabled.")
            session.call(lambda sp: sp.start_playback(context_uri=playlist_uri))
            print(f"Playing playlist: {playlist_uri} starting from the first track")


def enable_shuffle():
    if check_active_device():
        session.call(lambda sp: sp.shuffle(state=True))
        print("Shuffle mode enabled for subsequent tracks.")


def search_song(song, artist):
    query = f"track:{song} artist:{artist}"
    results = session.call(lambda sp: sp.search(q=query, limit=1))

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
        playlist = session.call(lambda sp: sp.playlist(playlist_name_or_id))

        if not args.play:
            print(f"Displaying tracks for playlist: {playlist['name']}")
            display_playlist_tracks(playlist["id"])
        if args.play:
            play_playlist(playlist["uri"])
    except Exception as e:
        print(f"Error fetching playlist by ID: {e}")
        print(f"Attempting to search for playlist by name: {playlist_name_or_id}")

        playlists = session.call(lambda sp: sp.current_user_playlists())
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
    results = session.call(lambda sp: sp.playlist_tracks(playlist_id))

    for idx, item in enumerate(results["items"]):
        track = item["track"]
        print(f"{idx + 1}. ", end="")
        display_track_info(track)


def run_rfid_loop():
    reader = SimpleMFRC522()

    print("Jukebox is ready. Tap a card to play music.")

    try:
        while True:
            print("Waiting for RFID scan...")
            scanned_id = reader.read()[0]
            print(f"Scanned RFID UID: {scanned_id}")

            uri = RFID_MAPPING.get(scanned_id)
            if uri:
                try:
                    if "track" in uri:
                        play_song(uri)
                    else:
                        play_playlist(uri)
                except RuntimeError as exc:
                    print(exc)
                    print(f"Playback paused until you run: {REAUTH_COMMAND}")
            else:
                print(f"No playlist mapped for RFID: {scanned_id}")

            sleep(1)
    except KeyboardInterrupt:
        print("\nExiting RFID jukebox.")
    except Exception as e:
        print(f"Unhandled error: {e}")
        raise
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    if args.reauth:
        print("Spotify re-authentication complete.")
    elif args.rfid:
        run_rfid_loop()
    elif args.song and args.artist:
        search_song(args.song, args.artist)
    elif args.playlist:
        if args.random:
            enable_shuffle()
        search_playlist(args.playlist)
    else:
        print("Provide --rfid, --reauth, or --song/--artist, or --playlist.")
