"""
Configuration module using Pydantic Settings.
Reads from .env file and environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_gta_music_dir() -> str:
    """Return the default GTA V User Music directory on Windows."""
    docs = Path(os.path.expanduser("~/Documents"))
    return str(docs / "Rockstar Games" / "GTA V" / "User Music")


class Settings(BaseSettings):
    """Application settings loaded from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Spotify
    spotify_client_id: str = Field(default="", description="Spotify API Client ID")
    spotify_client_secret: str = Field(default="", description="Spotify API Client Secret")
    spotify_redirect_uri: str = Field(
        default="https://127.0.0.1:8888/callback",
        description="Spotify OAuth redirect URI",
    )

    # GTA V
    gta_music_dir: str = Field(
        default_factory=_default_gta_music_dir,
        description="Path to GTA V Self Radio music folder",
    )

    # Download
    max_concurrent_downloads: int = Field(default=3, ge=1, le=10)
    audio_bitrate: int = Field(default=320, description="MP3 bitrate in kbps")
    audio_format: str = Field(default="mp3", description="Output audio format")

    # Sync
    watch_interval_seconds: int = Field(default=300, ge=30, description="Playlist watch interval")

    @field_validator("gta_music_dir", mode="before")
    @classmethod
    def resolve_gta_dir(cls, v: str) -> str:
        if not v:
            return _default_gta_music_dir()
        return str(Path(v).expanduser().resolve())

    @property
    def spotify_configured(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    def ensure_music_dir(self) -> Path:
        """Create the GTA music directory if it doesn't exist and return it."""
        p = Path(self.gta_music_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


def load_settings() -> Settings:
    """Load and return application settings."""
    return Settings()
