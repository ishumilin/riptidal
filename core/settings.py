"""
Settings management for RIPTIDAL.

This module provides classes and functions for managing application settings
using Pydantic for validation and type checking.
"""

import json
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Union, List, Dict, Any

from pydantic import BaseModel, Field, field_validator, ConfigDict

from riptidal.utils.paths import get_config_dir, get_default_download_dir


class AudioQuality(str, Enum):
    """Audio quality options for downloads."""
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    HIFI = "HIFI"
    MASTER = "MASTER"
    MAX = "MAX"  # Will try to get the highest available quality


class VideoQuality(str, Enum):
    """Video quality options for downloads."""
    P360 = "360"
    P480 = "480"
    P720 = "720"
    P1080 = "1080"
    MAX = "MAX"  # Will try to get the highest available quality


class Settings(BaseModel):
    """
    Application settings model.
    
    This class defines all the settings available in the application,
    with default values and validation.
    """
    # Download settings
    download_path: Path = Field(default_factory=get_default_download_dir)
    audio_quality: AudioQuality = AudioQuality.HIGH
    video_quality: VideoQuality = VideoQuality.P720
    quality_fallback: bool = True
    
    # Playlist settings
    enable_playlists: bool = True
    playlist_path_format: str = "Playlists/{playlist_name}"
    download_full_albums: bool = False
    create_m3u_playlists: bool = True
    
    # Track settings
    track_path_format: str = "{artist_name}/{album_name}/{track_number} - {track_title}"
    
    # Network settings
    connection_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5
    
    # Authentication settings
    auth_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expiry: Optional[int] = None
    user_id: Optional[str] = None
    country_code: Optional[str] = None
    
    # API settings
    api_key_index: int = 4

    # Matching behavior for library existence checks: "id" or "id_or_metadata"
    match_mode: str = "id_or_metadata"
    
    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True
    )
    
    @field_validator("download_path", mode='before')
    def validate_download_path(cls, v):
        """Validate and convert download path to Path object."""
        if isinstance(v, str):
            path = Path(v)
        elif isinstance(v, Path):
            path = v
        else:
            raise ValueError(f"Invalid path type: {type(v)}")
        
        # Ensure the directory exists
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @field_validator("playlist_path_format", "track_path_format")
    def validate_path_format(cls, v):
        """Validate path format strings."""
        if not v:
            raise ValueError("Path format cannot be empty")
        return v

    @field_validator("match_mode")
    def validate_match_mode(cls, v: str):
        """Validate match mode setting."""
        allowed = {"id", "id_or_metadata"}
        if v not in allowed:
            raise ValueError(f"match_mode must be one of {allowed}")
        return v


def load_settings(config_path: Optional[Union[str, Path]] = None) -> Settings:
    """
    Load settings from a configuration file.
    
    Args:
        config_path: Optional path to a configuration file
        
    Returns:
        Settings object with loaded values
    """
    # Determine the config file path
    if config_path:
        config_file = Path(config_path)
    else:
        config_file = get_config_dir() / "settings.json"
    
    # Load settings from file if it exists
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return Settings(**config_data)
        except (json.JSONDecodeError, ValueError) as e:
            import logging
            logging.getLogger(__name__).error(f"Error loading settings: {e}")
            return Settings()
    
    return Settings()


def save_settings(settings: Settings, config_path: Optional[Union[str, Path]] = None) -> None:
    """
    Save settings to a configuration file.
    
    Args:
        settings: Settings object to save
        config_path: Optional path to a configuration file
    """
    # Determine the config file path
    if config_path:
        config_file = Path(config_path)
    else:
        config_file = get_config_dir() / "settings.json"
    
    # Ensure the directory exists
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save settings to file
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(mode='json'), f, indent=2)
