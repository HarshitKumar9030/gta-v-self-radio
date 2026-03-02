"""
Sync engine – orchestrates Spotify ↔ GTA V Self Radio synchronization.
Manages state tracking, incremental syncs, and watch mode.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from gta_radio.config import Settings
from gta_radio.downloader import DownloadResult, YouTubeDownloader
from gta_radio.spotify_client import Playlist, SpotifyClient, Track

console = Console()

STATE_FILE = ".sync_state.json"


@dataclass
class SyncState:
    """Persisted state to enable incremental syncs."""

    synced_track_ids: set[str] = field(default_factory=set)
    last_sync: Optional[str] = None
    playlist_id: Optional[str] = None
    playlist_name: Optional[str] = None

    def save(self) -> None:
        data = {
            "synced_track_ids": list(self.synced_track_ids),
            "last_sync": self.last_sync,
            "playlist_id": self.playlist_id,
            "playlist_name": self.playlist_name,
        }
        Path(STATE_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> SyncState:
        p = Path(STATE_FILE)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(
                synced_track_ids=set(data.get("synced_track_ids", [])),
                last_sync=data.get("last_sync"),
                playlist_id=data.get("playlist_id"),
                playlist_name=data.get("playlist_name"),
            )
        except Exception:
            return cls()


class SyncEngine:
    """Orchestrates the playlist-to-folder sync pipeline."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.spotify = SpotifyClient(settings)
        self.downloader = YouTubeDownloader(settings)
        self.state = SyncState.load()

    def authenticate(self) -> bool:
        return self.spotify.authenticate()

    def list_playlists(self) -> list[Playlist]:
        """Fetch and display available playlists."""
        playlists = self.spotify.get_playlists()
        if not playlists:
            console.print("[yellow]No playlists found.[/]")
            return playlists

        table = Table(title="Your Spotify Playlists", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold cyan")
        table.add_column("Owner", style="green")
        table.add_column("Tracks", justify="right", style="magenta")

        for i, pl in enumerate(playlists, 1):
            table.add_row(str(i), pl.name, pl.owner, str(pl.total_tracks))

        console.print(table)
        return playlists

    def sync_playlist(
        self,
        playlist_id: str,
        force: bool = False,
        cleanup: bool = False,
    ) -> None:
        """Sync a Spotify playlist to the GTA V Self Radio folder."""
        console.print()
        console.print(
            Panel(
                f"[bold]Syncing to:[/] {self.settings.gta_music_dir}",
                title="GTA V Self Radio Sync",
                border_style="blue",
            )
        )

        # Fetch tracks
        with console.status("[bold cyan]Fetching playlist tracks from Spotify..."):
            tracks = self.spotify.get_playlist_tracks(playlist_id)

        console.print(f"[bold green]✓[/] Found [cyan]{len(tracks)}[/] tracks in playlist")

        # Determine which tracks need downloading
        if force:
            to_download = tracks
        else:
            to_download = [
                t for t in tracks if not self.downloader.is_already_downloaded(t)
            ]

        already_have = len(tracks) - len(to_download)
        if already_have > 0:
            console.print(
                f"[dim]  Skipping {already_have} already downloaded track(s)[/]"
            )

        if not to_download:
            console.print("[bold green]✓[/] All tracks are already synced!")
            self._update_state(playlist_id, tracks)
            return

        console.print(f"[bold]Downloading {len(to_download)} track(s)...[/]\n")

        # Download with progress
        success_count = 0
        fail_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=len(to_download))

            def on_complete(track: Track, result: DownloadResult) -> None:
                nonlocal success_count, fail_count
                if result.success:
                    success_count += 1
                    progress.update(
                        task,
                        advance=1,
                        description=f"[green]✓[/] {track.name[:50]}",
                    )
                else:
                    fail_count += 1
                    progress.update(
                        task,
                        advance=1,
                        description=f"[red]✗[/] {track.name[:50]}",
                    )

            self.downloader.download_tracks(to_download, progress_callback=on_complete)

        # Clean up removed tracks
        if cleanup:
            console.print("\n[dim]Cleaning up tracks no longer in playlist...[/]")
            removed = self.downloader.cleanup_removed_tracks(tracks)
            if removed:
                console.print(f"[yellow]Removed {len(removed)} old track(s)[/]")

        # Summary
        console.print()
        console.print(
            Panel(
                f"[bold green]✓ {success_count}[/] downloaded  "
                f"[bold red]✗ {fail_count}[/] failed  "
                f"[dim]{already_have} skipped[/]",
                title="Sync Complete",
                border_style="green" if fail_count == 0 else "yellow",
            )
        )

        self._update_state(playlist_id, tracks)

    def sync_liked_songs(self, limit: int = 50, force: bool = False) -> None:
        """Sync the user's Liked Songs to GTA V Self Radio."""
        console.print()
        console.print(
            Panel(
                f"[bold]Syncing Liked Songs to:[/] {self.settings.gta_music_dir}",
                title="GTA V Self Radio – Liked Songs",
                border_style="blue",
            )
        )

        with console.status("[bold cyan]Fetching Liked Songs from Spotify..."):
            tracks = self.spotify.get_liked_songs(limit=limit)

        console.print(f"[bold green]✓[/] Found [cyan]{len(tracks)}[/] liked songs")

        # Reuse the same download logic
        if force:
            to_download = tracks
        else:
            to_download = [
                t for t in tracks if not self.downloader.is_already_downloaded(t)
            ]

        already_have = len(tracks) - len(to_download)
        if already_have > 0:
            console.print(f"[dim]  Skipping {already_have} already downloaded[/]")

        if not to_download:
            console.print("[bold green]✓[/] All liked songs are already synced!")
            return

        console.print(f"[bold]Downloading {len(to_download)} track(s)...[/]\n")

        success_count = 0
        fail_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading", total=len(to_download))

            def on_complete(track: Track, result: DownloadResult) -> None:
                nonlocal success_count, fail_count
                if result.success:
                    success_count += 1
                    progress.update(task, advance=1, description=f"[green]✓[/] {track.name[:50]}")
                else:
                    fail_count += 1
                    progress.update(task, advance=1, description=f"[red]✗[/] {track.name[:50]}")

            self.downloader.download_tracks(to_download, progress_callback=on_complete)

        console.print()
        console.print(
            Panel(
                f"[bold green]✓ {success_count}[/] downloaded  "
                f"[bold red]✗ {fail_count}[/] failed  "
                f"[dim]{already_have} skipped[/]",
                title="Sync Complete",
                border_style="green" if fail_count == 0 else "yellow",
            )
        )

    def watch(self, playlist_id: str) -> None:
        """Continuously watch a playlist for changes and re-sync."""
        interval = self.settings.watch_interval_seconds
        console.print(
            f"\n[bold cyan]👁  Watch mode[/] — checking every "
            f"{interval}s for changes. Press Ctrl+C to stop.\n"
        )

        try:
            while True:
                self.sync_playlist(playlist_id, cleanup=True)
                console.print(
                    f"\n[dim]Next check in {interval}s "
                    f"(Ctrl+C to stop)...[/]\n"
                )
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Watch mode stopped.[/]")

    def _update_state(self, playlist_id: str, tracks: list[Track]) -> None:
        """Persist sync state."""
        self.state.playlist_id = playlist_id
        self.state.synced_track_ids = {t.id for t in tracks}
        self.state.last_sync = datetime.now().isoformat()
        self.state.save()
