"""Spotify OAuth with automatic refresh and invalid_grant recovery."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, TypeVar

import spotipy
from spotipy.exceptions import SpotifyException, SpotifyOauthError
from spotipy.oauth2 import SpotifyOAuth

SCOPE = ",".join([
    "user-library-read",
    "user-read-playback-state",
    "user-modify-playback-state",
    "playlist-read-private",
])

REAUTH_COMMAND = "python jukebox.py --reauth"
REAUTH_MESSAGE = (
    "Spotify refresh token expired or revoked. "
    f"Run: {REAUTH_COMMAND}"
)

T = TypeVar("T")


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ if not already set."""
    env_path = path or Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def token_cache_path(app_dir: Path) -> Path:
    return app_dir / ".cache"


def is_invalid_grant_error(exc: BaseException) -> bool:
    if isinstance(exc, SpotifyOauthError):
        error = getattr(exc, "error", None)
        if error and str(error).lower() == "invalid_grant":
            return True
    return "invalid_grant" in str(exc).lower()


def discard_token_cache(cache_path: Path) -> None:
    if cache_path.is_file():
        cache_path.unlink()
        print(f"Discarded stored Spotify token: {cache_path}")


def _require_credentials() -> tuple[str, str, str]:
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.environ.get(
        "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
    )

    if not client_id or not client_secret:
        raise RuntimeError(
            "Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in .env "
            "(see .env.example)"
        )

    if "localhost" in redirect_uri:
        raise RuntimeError(
            "SPOTIPY_REDIRECT_URI cannot use localhost. "
            "Use http://127.0.0.1:8888/callback and add the same URI in your "
            "Spotify app settings."
        )

    return client_id, client_secret, redirect_uri


def _validate_callback_url(url: str) -> None:
    if "accounts.spotify.com/authorize" in url:
        raise RuntimeError(
            "That is the sign-in URL, not the redirect URL.\n\n"
            "After you approve access, Spotify sends your browser to a URL like:\n"
            "  http://127.0.0.1:8888/callback?code=...\n\n"
            "Copy that full URL from your browser's address bar. "
            "The page may show a connection error — that is fine."
        )

    if "code=" not in url and "error=" not in url:
        raise RuntimeError(
            "The pasted URL does not contain an authorization code.\n"
            "Paste the full redirect URL from your browser after approving access."
        )


def create_auth_manager(app_dir: Path, *, show_dialog: bool = False) -> SpotifyOAuth:
    client_id, client_secret, redirect_uri = _require_credentials()
    cache_path = token_cache_path(app_dir)

    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_path=str(cache_path),
        open_browser=False,
        show_dialog=show_dialog,
    )


def run_sign_in_flow(auth_manager: SpotifyOAuth, *, force_prompt: bool = False) -> None:
    """Run the authorization code flow for headless environments."""
    if force_prompt:
        auth_manager.show_dialog = True

    auth_url = auth_manager.get_authorize_url()
    print("\nSpotify sign-in required.")
    print("1. Open this URL in a browser, log in, and approve access:\n")
    print(auth_url)
    print(
        "\n2. After approving, your browser will redirect to a URL like:\n"
        f"   {auth_manager.redirect_uri}?code=...\n"
        "   The page may fail to load — copy the full URL from the address bar.\n"
    )

    redirect_url = input("Paste the redirect URL here: ").strip()
    if not redirect_url:
        raise RuntimeError("No redirect URL provided.")

    _validate_callback_url(redirect_url)

    code = auth_manager.parse_response_code(redirect_url)
    token = auth_manager.get_access_token(code, as_dict=False)
    if not token:
        raise RuntimeError("Failed to obtain Spotify access token.")

    print("Spotify authorization successful.\n")


def ensure_authenticated(
    auth_manager: SpotifyOAuth,
    cache_path: Path,
    *,
    interactive: bool,
    force_sign_in: bool = False,
) -> None:
    """Load, refresh, or replace the stored token."""
    if force_sign_in:
        discard_token_cache(cache_path)
        run_sign_in_flow(auth_manager, force_prompt=True)
        return

    cached = auth_manager.get_cached_token()
    if cached is None:
        if interactive:
            run_sign_in_flow(auth_manager)
            return
        raise RuntimeError(f"No Spotify token found. Run: {REAUTH_COMMAND}")

    try:
        token = auth_manager.get_access_token(as_dict=False)
    except SpotifyOauthError as exc:
        if not is_invalid_grant_error(exc):
            raise
        discard_token_cache(cache_path)
        if interactive:
            run_sign_in_flow(auth_manager, force_prompt=True)
            return
        raise RuntimeError(REAUTH_MESSAGE) from exc

    if not token:
        discard_token_cache(cache_path)
        if interactive:
            run_sign_in_flow(auth_manager, force_prompt=True)
            return
        raise RuntimeError(REAUTH_MESSAGE)


class SpotifySession:
    """Spotify client wrapper that handles expired refresh tokens."""

    def __init__(
        self,
        app_dir: Path,
        *,
        force_reauth: bool = False,
        interactive: bool = False,
    ):
        self.app_dir = app_dir
        self.cache_path = token_cache_path(app_dir)
        self.interactive = interactive
        self.auth_manager = create_auth_manager(app_dir)
        ensure_authenticated(
            self.auth_manager,
            self.cache_path,
            interactive=interactive,
            force_sign_in=force_reauth,
        )
        self.client = spotipy.Spotify(auth_manager=self.auth_manager)

    def call(self, fn: Callable[[spotipy.Spotify], T]) -> T:
        try:
            return fn(self.client)
        except SpotifyOauthError as exc:
            if not is_invalid_grant_error(exc):
                raise
            return self._recover_from_invalid_grant(fn, exc)
        except SpotifyException as exc:
            if not is_invalid_grant_error(exc):
                raise
            return self._recover_from_invalid_grant(fn, exc)

    def _recover_from_invalid_grant(
        self,
        fn: Callable[[spotipy.Spotify], T],
        exc: BaseException,
    ) -> T:
        discard_token_cache(self.cache_path)

        if self.interactive:
            print("Stored Spotify token is no longer valid.")
            run_sign_in_flow(self.auth_manager, force_prompt=True)
            return fn(self.client)

        raise RuntimeError(REAUTH_MESSAGE) from exc


def create_session(
    app_dir: Path,
    *,
    force_reauth: bool = False,
    interactive: bool | None = None,
) -> SpotifySession:
    if interactive is None:
        interactive = sys.stdin.isatty()
    return SpotifySession(
        app_dir,
        force_reauth=force_reauth,
        interactive=interactive or force_reauth,
    )
