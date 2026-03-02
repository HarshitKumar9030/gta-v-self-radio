"""
Spotify authentication and playlist fetching module.
Uses OAuth2 Authorization Code flow with URL-paste callback.
"""

from __future__ import annotations

import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from rich.console import Console

from gta_radio.config import Settings

console = Console()

SCOPE = "playlist-read-private playlist-read-collaborative user-library-read"


@dataclass
class Track:
    """Represents a single Spotify track."""

    id: str
    name: str
    artists: list[str]
    album: str
    duration_ms: int
    uri: str

    @property
    def search_query(self) -> str:
        """Build a YouTube search query from track metadata."""
        artist_str = ", ".join(self.artists)
        return f"{self.name} - {artist_str}"

    @property
    def safe_filename(self) -> str:
        """Return a filesystem-safe filename (without extension)."""
        artist_str = ", ".join(self.artists[:2])
        raw = f"{artist_str} - {self.name}"
        # Remove characters not allowed in Windows filenames
        for ch in r'<>:"/\|?*':
            raw = raw.replace(ch, "")
        return raw.strip()[:200]  # cap at 200 chars


@dataclass
class Playlist:
    """Represents a Spotify playlist."""

    id: str
    name: str
    owner: str
    total_tracks: int
    tracks: list[Track] = field(default_factory=list)


class SpotifyClient:
    """Handles Spotify authentication and data fetching."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sp: Optional[spotipy.Spotify] = None

    @staticmethod
    def _extract_code_from_url(url: str) -> str | None:
        """Extract the 'code' query parameter from a callback URL."""
        try:
            parsed = urlparse(url.strip())
            params = parse_qs(parsed.query)
            codes = params.get("code", [])
            return codes[0] if codes else None
        except Exception:
            return None

    def authenticate(self) -> bool:
        """Perform Spotify OAuth2 authentication via URL-paste flow."""
        if not self.settings.spotify_configured:
            console.print(
                "[bold red]Error:[/] Spotify credentials not configured.\n"
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file.\n"
                "Get them from https://developer.spotify.com/dashboard"
            )
            return False

        try:
            auth_manager = SpotifyOAuth(
                client_id=self.settings.spotify_client_id,
                client_secret=self.settings.spotify_client_secret,
                redirect_uri=self.settings.spotify_redirect_uri,
                scope=SCOPE,
                cache_path=".spotify_cache",
                open_browser=False,
            )

            # Check for cached token first
            token_info = auth_manager.cache_handler.get_cached_token()
            if token_info and not auth_manager.is_token_expired(token_info):
                self._sp = spotipy.Spotify(auth_manager=auth_manager)
                user = self._sp.current_user()
                console.print(
                    f"[bold green]✓[/] Authenticated as [cyan]{user['display_name']}[/] "
                    f"({user['id']}) [dim](cached token)[/]"
                )
                return True

            # No valid token — start OAuth flow
            auth_url = auth_manager.get_authorize_url()

            console.print(
                "[bold]Opening browser for Spotify login...[/]\n"
                "[dim]If it doesn't open, visit this URL:[/]\n"
                f"[link={auth_url}]{auth_url}[/link]\n"
            )

            webbrowser.open(auth_url)

            console.print(
                "[bold yellow]After logging in, your browser will show a \"can't connect\" page.[/]\n"
                "[bold]That's expected! Copy the full URL from the address bar and paste it below.[/]\n"
                "[dim]It looks like: https://127.0.0.1:8888/callback?code=AQD...[/]\n"
            )

            auth_code = None
            for attempt in range(3):
                try:
                    pasted_url = input("Paste the redirect URL here: ").strip()
                    if not pasted_url:
                        continue
                    auth_code = self._extract_code_from_url(pasted_url)
                    if auth_code:
                        break
                    console.print("[red]Could not find auth code in that URL. Try again.[/]")
                except (EOFError, KeyboardInterrupt):
                    break

            if not auth_code:
                console.print("[bold red]Authentication failed — no auth code received.[/]")
                return False

            # Exchange the code for an access token
            token_info = auth_manager.get_access_token(auth_code, as_dict=True)

            self._sp = spotipy.Spotify(auth_manager=auth_manager)

            # Verify authentication
            user = self._sp.current_user()
            console.print(
                f"[bold green]✓[/] Authenticated as [cyan]{user['display_name']}[/] "
                f"({user['id']})"
            )
            return True

        except Exception as e:
            console.print(f"[bold red]Authentication failed:[/] {e}")
            return False

    @property
    def sp(self) -> spotipy.Spotify:
        """Return the authenticated Spotify client."""
        if self._sp is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._sp

    def get_playlists(self) -> list[Playlist]:
        """Fetch all playlists for the current user."""
        playlists: list[Playlist] = []
        results = self.sp.current_user_playlists(limit=50)

        while results:
            for item in results["items"]:
                playlists.append(
                    Playlist(
                        id=item["id"],
                        name=item["name"],
                        owner=item["owner"]["display_name"],
                        total_tracks=item["tracks"]["total"],
                    )
                )
            if results["next"]:
                results = self.sp.next(results)
            else:
                break

        return playlists

    def get_liked_songs(self, limit: int = 0) -> list[Track]:
        """Fetch user's Liked Songs. If limit=0, fetch all."""
        tracks: list[Track] = []
        results = self.sp.current_user_saved_tracks(limit=50)

        while results:
            for item in results["items"]:
                t = item["track"]
                if t is None:
                    continue
                tracks.append(self._parse_track(t))

                if limit and len(tracks) >= limit:
                    return tracks[:limit]

            if results["next"]:
                results = self.sp.next(results)
            else:
                break

        return tracks

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """Fetch all tracks from a specific playlist."""
        tracks: list[Track] = []
        results = self.sp.playlist_tracks(playlist_id, limit=100)

        while results:
            for item in results["items"]:
                t = item.get("track")
                if t is None or t.get("id") is None:
                    continue  # skip local files / unavailable tracks
                tracks.append(self._parse_track(t))

            if results["next"]:
                results = self.sp.next(results)
            else:
                break

        return tracks

    @staticmethod
    def _parse_track(t: dict) -> Track:
        """Parse a Spotify track dict into a Track dataclass."""
        return Track(
            id=t["id"],
            name=t["name"],
            artists=[a["name"] for a in t.get("artists", [])],
            album=t.get("album", {}).get("name", "Unknown"),
            duration_ms=t.get("duration_ms", 0),
            uri=t.get("uri", ""),
        )
