"""
YouTube audio downloader module.
Uses yt-dlp to search YouTube and download audio as MP3.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yt_dlp
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from gta_radio.config import Settings
from gta_radio.spotify_client import Track

console = Console()


@dataclass
class DownloadResult:
    """Result of a single download attempt."""

    track: Track
    success: bool
    file_path: Optional[Path] = None
    error: Optional[str] = None


class YouTubeDownloader:
    """Downloads audio from YouTube using yt-dlp."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.output_dir = settings.ensure_music_dir()
        self._lock = threading.Lock()

    def _get_ydl_opts(self, output_path: str) -> dict:
        """Build yt-dlp options."""
        return {
            "format": "bestaudio/best",
            "extractaudio": True,
            "audioformat": self.settings.audio_format,
            "audioquality": 0,  # best
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "default_search": "ytsearch1",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.settings.audio_format,
                    "preferredquality": str(self.settings.audio_bitrate),
                }
            ],
            # Limit duration to 15 minutes to avoid downloading full albums/movies
            "match_filter": yt_dlp.utils.match_filter_func("duration < 900"),
        }

    def is_already_downloaded(self, track: Track) -> bool:
        """Check if a track has already been downloaded."""
        expected_path = self.output_dir / f"{track.safe_filename}.{self.settings.audio_format}"
        return expected_path.exists()

    def download_track(
        self,
        track: Track,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> DownloadResult:
        """Download a single track from YouTube."""
        filename = track.safe_filename
        output_path = str(self.output_dir / filename)
        final_path = self.output_dir / f"{filename}.{self.settings.audio_format}"

        # Skip if already downloaded
        if final_path.exists():
            return DownloadResult(
                track=track,
                success=True,
                file_path=final_path,
            )

        search_query = track.search_query
        ydl_opts = self._get_ydl_opts(output_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Search and download
                ydl.download([f"ytsearch1:{search_query}"])

            # Verify download
            if not final_path.exists():
                # yt-dlp may append different extensions; look for the file
                found = list(self.output_dir.glob(f"{filename}.*"))
                if found:
                    final_path = found[0]
                else:
                    return DownloadResult(
                        track=track,
                        success=False,
                        error="File not found after download",
                    )

            # Tag the MP3 file with metadata
            self._tag_file(final_path, track)

            return DownloadResult(
                track=track,
                success=True,
                file_path=final_path,
            )

        except Exception as e:
            # Clean up partial downloads
            for f in self.output_dir.glob(f"{filename}.*"):
                if f.suffix in (".part", ".tmp", ".temp"):
                    f.unlink(missing_ok=True)

            return DownloadResult(
                track=track,
                success=False,
                error=str(e),
            )

    def _tag_file(self, file_path: Path, track: Track) -> None:
        """Write ID3 tags to the downloaded MP3 file."""
        if file_path.suffix.lower() != ".mp3":
            return

        try:
            try:
                audio = EasyID3(str(file_path))
            except ID3NoHeaderError:
                audio = MP3(str(file_path))
                audio.add_tags()
                audio.save()
                audio = EasyID3(str(file_path))

            audio["title"] = track.name
            audio["artist"] = ", ".join(track.artists)
            audio["album"] = track.album
            audio.save()
        except Exception:
            pass  # Non-critical; tagging failure shouldn't stop the process

    def download_tracks(
        self,
        tracks: list[Track],
        progress_callback: Optional[Callable[[Track, DownloadResult], None]] = None,
    ) -> list[DownloadResult]:
        """
        Download multiple tracks with concurrency control.
        Returns list of DownloadResult.
        """
        results: list[DownloadResult] = []
        max_workers = self.settings.max_concurrent_downloads

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_track = {
                executor.submit(self.download_track, track): track
                for track in tracks
            }

            for future in concurrent.futures.as_completed(future_to_track):
                track = future_to_track[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = DownloadResult(
                        track=track, success=False, error=str(e)
                    )

                results.append(result)

                if progress_callback:
                    progress_callback(track, result)

        return results

    def cleanup_removed_tracks(
        self,
        current_tracks: list[Track],
    ) -> list[Path]:
        """Remove files that are no longer in the playlist."""
        current_filenames = {
            f"{t.safe_filename}.{self.settings.audio_format}" for t in current_tracks
        }

        removed: list[Path] = []
        for f in self.output_dir.iterdir():
            if f.is_file() and f.suffix.lower() == f".{self.settings.audio_format}":
                if f.name not in current_filenames:
                    f.unlink()
                    removed.append(f)

        return removed
