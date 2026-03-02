"""
CLI interface for GTA V Self Radio Spotify Relay.
Built with Click + Rich for a beautiful terminal experience.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from gta_radio.config import load_settings
from gta_radio.sync_engine import SyncEngine

console = Console()

BANNER = r"""
  ________________________    ____   ____ __________             .___.__        
 /  _____/\__    ___/  _  \   \   \ /   / \______   \_____     __| _/|__| ____  
/   \  ___  |    | /  /_\  \   \   Y   /   |       _/\__  \   / __ | |  |/  _ \ 
\    \_\  \ |    |/    |    \   \     /    |    |   \ / __ \_/ /_/ | |  (  <_> )
 \______  / |____|\____|__  /    \___/     |____|_  /(____  /\____ | |__|\____/ 
        \/                \/                      \/      \/      \/            
      ♫  Spotify → GTA V Self Radio Relay  ♫
"""


def print_banner() -> None:
    console.print(
        Panel(
            Text(BANNER, style="bold cyan"),
            border_style="blue",
            padding=(0, 2),
        )
    )


@click.group()
@click.version_option(version="1.0.0", prog_name="gta-radio")
def main() -> None:
    """GTA V Self Radio Spotify Relay — sync Spotify playlists to GTA V."""
    pass


@main.command()
def auth() -> None:
    """Authenticate with Spotify."""
    print_banner()
    settings = load_settings()
    engine = SyncEngine(settings)

    if engine.authenticate():
        console.print("[bold green]✓[/] Authentication successful! You're ready to sync.")
    else:
        console.print("[bold red]✗[/] Authentication failed.")
        sys.exit(1)


@main.command()
def playlists() -> None:
    """List your Spotify playlists."""
    print_banner()
    settings = load_settings()
    engine = SyncEngine(settings)

    if not engine.authenticate():
        sys.exit(1)

    engine.list_playlists()


@main.command()
@click.option(
    "--playlist", "-p", "playlist_id",
    help="Spotify playlist ID or URL to sync.",
)
@click.option(
    "--liked", "-l",
    is_flag=True,
    default=False,
    help="Sync your Liked Songs instead of a playlist.",
)
@click.option(
    "--limit", "-n",
    type=int,
    default=50,
    help="Max number of Liked Songs to sync (default: 50, 0=all).",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Force re-download of all tracks (ignore cache).",
)
@click.option(
    "--cleanup/--no-cleanup",
    default=False,
    help="Remove tracks no longer in the playlist.",
)
@click.option(
    "--interactive", "-i",
    is_flag=True,
    default=False,
    help="Interactively choose a playlist to sync.",
)
def sync(
    playlist_id: str | None,
    liked: bool,
    limit: int,
    force: bool,
    cleanup: bool,
    interactive: bool,
) -> None:
    """Sync a Spotify playlist to GTA V Self Radio."""
    print_banner()
    settings = load_settings()
    engine = SyncEngine(settings)

    if not engine.authenticate():
        sys.exit(1)

    if liked:
        engine.sync_liked_songs(limit=limit, force=force)
        _post_sync_hint()
        return

    # Resolve playlist ID
    resolved_id = _resolve_playlist_id(engine, playlist_id, interactive)
    if not resolved_id:
        console.print("[bold red]No playlist selected.[/]")
        sys.exit(1)

    engine.sync_playlist(resolved_id, force=force, cleanup=cleanup)
    _post_sync_hint()


@main.command()
@click.option(
    "--playlist", "-p", "playlist_id",
    help="Spotify playlist ID or URL to watch.",
)
@click.option(
    "--interactive", "-i",
    is_flag=True,
    default=False,
    help="Interactively choose a playlist to watch.",
)
def watch(playlist_id: str | None, interactive: bool) -> None:
    """Watch a playlist for changes and auto-sync."""
    print_banner()
    settings = load_settings()
    engine = SyncEngine(settings)

    if not engine.authenticate():
        sys.exit(1)

    resolved_id = _resolve_playlist_id(engine, playlist_id, interactive)
    if not resolved_id:
        console.print("[bold red]No playlist selected.[/]")
        sys.exit(1)

    engine.watch(resolved_id)


@main.command()
def status() -> None:
    """Show current sync status and configuration."""
    print_banner()
    settings = load_settings()

    from gta_radio.sync_engine import SyncState

    state = SyncState.load()

    console.print(Panel("[bold]Configuration[/]", border_style="blue"))
    console.print(f"  Music folder:   [cyan]{settings.gta_music_dir}[/]")
    console.print(f"  Audio format:   [cyan]{settings.audio_format}[/]")
    console.print(f"  Bitrate:        [cyan]{settings.audio_bitrate} kbps[/]")
    console.print(f"  Concurrency:    [cyan]{settings.max_concurrent_downloads}[/]")
    console.print(f"  Watch interval: [cyan]{settings.watch_interval_seconds}s[/]")
    console.print()

    music_dir = Path(settings.gta_music_dir)
    if music_dir.exists():
        files = list(music_dir.glob(f"*.{settings.audio_format}"))
        console.print(
            f"  Files in Self Radio: [bold green]{len(files)}[/] "
            f".{settings.audio_format} file(s)"
        )
    else:
        console.print("  [yellow]Music folder does not exist yet.[/]")

    if state.last_sync:
        console.print(f"\n  Last sync:      [cyan]{state.last_sync}[/]")
        console.print(f"  Playlist:       [cyan]{state.playlist_name or state.playlist_id or 'N/A'}[/]")
        console.print(f"  Synced tracks:  [cyan]{len(state.synced_track_ids)}[/]")
    else:
        console.print("\n  [dim]No sync has been performed yet.[/]")


@main.command()
def setup() -> None:
    """Interactive first-time setup wizard."""
    print_banner()
    console.print(Panel("[bold]First-Time Setup[/]", border_style="green"))
    console.print()

    # Check for .env
    env_path = Path(".env")
    if env_path.exists():
        console.print("[green]✓[/] .env file found")
    else:
        console.print("[yellow]Creating .env from template...[/]")
        example = Path(".env.example")
        if example.exists():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            console.print("[green]✓[/] Created .env — please edit it with your Spotify credentials")
        else:
            console.print("[red]✗[/] .env.example not found")

    # Check for ffmpeg
    import shutil

    if shutil.which("ffmpeg"):
        console.print("[green]✓[/] ffmpeg found in PATH")
    else:
        console.print(
            "[bold red]✗[/] ffmpeg not found!\n"
            "  Install it: [cyan]winget install Gyan.FFmpeg[/]\n"
            "  Or download from https://ffmpeg.org/download.html"
        )

    # Check GTA V directory
    settings = load_settings()
    music_dir = Path(settings.gta_music_dir)
    if music_dir.exists():
        console.print(f"[green]✓[/] GTA V music folder exists: {music_dir}")
    else:
        console.print(f"[yellow]![/] GTA V music folder not found: {music_dir}")
        console.print("  It will be created automatically when you sync.")

    console.print()
    console.print(
        Panel(
            "Next steps:\n"
            "1. Edit [bold].env[/] with your Spotify API credentials\n"
            "2. Run [bold cyan]gta-radio auth[/] to authenticate\n"
            "3. Run [bold cyan]gta-radio sync -i[/] to sync a playlist",
            border_style="green",
        )
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_playlist_id(
    engine: SyncEngine,
    playlist_id: str | None,
    interactive: bool,
) -> str | None:
    """Resolve a playlist ID from URL, ID string, or interactive selection."""
    if playlist_id:
        return _extract_playlist_id(playlist_id)

    if interactive:
        playlists = engine.list_playlists()
        if not playlists:
            return None

        console.print()
        choice = click.prompt(
            "Enter playlist number to sync",
            type=click.IntRange(1, len(playlists)),
        )
        selected = playlists[choice - 1]
        console.print(f"\n[bold]Selected:[/] {selected.name}")
        return selected.id

    # Check saved state
    from gta_radio.sync_engine import SyncState

    state = SyncState.load()
    if state.playlist_id:
        console.print(
            f"[dim]Using last synced playlist: {state.playlist_name or state.playlist_id}[/]"
        )
        return state.playlist_id

    console.print("[yellow]No playlist specified. Use --playlist, --interactive, or --liked[/]")
    return None


def _extract_playlist_id(raw: str) -> str:
    """Extract a Spotify playlist ID from a URL or return as-is."""
    # Handle full Spotify URLs like:
    # https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
    if "spotify.com/playlist/" in raw:
        # Extract the ID between /playlist/ and the next / or ?
        part = raw.split("playlist/")[1]
        return part.split("?")[0].split("/")[0]
    # Handle spotify:playlist:ID URIs
    if raw.startswith("spotify:playlist:"):
        return raw.split(":")[-1]
    return raw


def _post_sync_hint() -> None:
    """Print a hint about refreshing Self Radio in GTA V."""
    console.print()
    console.print(
        Panel(
            "[bold]To hear new songs in GTA V:[/]\n\n"
            "1. Open GTA V → [cyan]Settings → Audio[/]\n"
            "2. Set [cyan]Self Radio[/] to [bold]Sequential[/] or [bold]Radio[/] mode\n"
            "3. Click [cyan]Quick Scan[/] or [cyan]Full Scan[/] under Self Radio\n"
            "4. Tune into [bold cyan]Self Radio[/] in-game! 🎶",
            title="💡 GTA V Tip",
            border_style="dim",
        )
    )


if __name__ == "__main__":
    main()
