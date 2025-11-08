"""
API models for RIPTIDAL.

This module defines Pydantic models for the Tidal API responses.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union

from pydantic import BaseModel, Field, field_validator


class ResourceType(str, Enum):
    """Types of resources in the Tidal API."""
    ALBUM = "ALBUM"
    TRACK = "TRACK"
    VIDEO = "VIDEO"
    ARTIST = "ARTIST"
    PLAYLIST = "PLAYLIST"
    MIX = "MIX"


class StreamQuality(str, Enum):
    """Stream quality options for audio from the Tidal API."""
    LOW = "LOW"
    HIGH = "HIGH"
    LOSSLESS = "LOSSLESS"
    HI_RES = "HI_RES"
    HI_RES_LOSSLESS = "HI_RES_LOSSLESS"
    MAX = "MAX"  # Will try to get the highest available quality


class VideoQuality(str, Enum):
    """Video quality options from the Tidal API."""
    P360 = "360"
    P480 = "480"
    P720 = "720"
    P1080 = "1080"
    MAX = "MAX"  # Will try to get the highest available quality


class Artist(BaseModel):
    """Artist model."""
    id: str
    name: str
    picture: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    
    @field_validator("id", mode='before')
    def validate_id(cls, v):
        """Convert integer ID to string."""
        return str(v) if v is not None else None


class Album(BaseModel):
    """Album model."""
    id: str
    title: str
    cover: Optional[str] = None
    releaseDate: Optional[str] = None
    numberOfTracks: Optional[int] = None
    numberOfVideos: Optional[int] = None
    duration: Optional[int] = None
    artists: List[Artist] = Field(default_factory=list)
    tracks: List['Track'] = Field(default_factory=list) # Add tracks field
    audioQuality: Optional[str] = None
    explicit: Optional[bool] = False
    
    @field_validator("id", mode='before')
    def validate_id(cls, v):
        """Convert integer ID to string."""
        return str(v) if v is not None else None
    
    @property
    def release_year(self) -> Optional[int]:
        """Extract the release year from the release date."""
        if self.releaseDate:
            try:
                return int(self.releaseDate.split("-")[0])
            except (ValueError, IndexError):
                pass
        return None


class Track(BaseModel):
    """Track model."""
    id: str
    title: str
    duration: Optional[int] = None
    trackNumber: Optional[int] = None
    volumeNumber: Optional[int] = None
    isrc: Optional[str] = None
    explicit: Optional[bool] = False
    audioQuality: Optional[str] = None
    copyRight: Optional[str] = None
    artist: Optional[Artist] = None
    artists: List[Artist] = Field(default_factory=list)
    album: Optional[Album] = None
    version: Optional[str] = None
    url: Optional[str] = None
    
    @field_validator("id", mode='before')
    def validate_id(cls, v):
        """Convert integer ID to string."""
        return str(v) if v is not None else None
    
    @property
    def formatted_title(self) -> str:
        """Get the formatted title including version if available."""
        if self.version:
            return f"{self.title} ({self.version})"
        return self.title
    
    @property
    def duration_formatted(self) -> str:
        """Format the duration as MM:SS."""
        if self.duration is None:
            return "00:00"
        
        seconds = self.duration // 1000
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def artist_names(self) -> str:
        """Get a comma-separated list of artist names."""
        if not self.artists:
            if self.artist:
                return self.artist.name
            return "Unknown Artist"
        
        return ", ".join(artist.name for artist in self.artists)


class Video(BaseModel):
    """Video model."""
    id: str
    title: str
    duration: Optional[int] = None
    quality: Optional[str] = None
    explicit: Optional[bool] = False
    artist: Optional[Artist] = None
    artists: List[Artist] = Field(default_factory=list)
    album: Optional[Album] = None
    version: Optional[str] = None
    url: Optional[str] = None
    
    @field_validator("id", mode='before')
    def validate_id(cls, v):
        """Convert integer ID to string."""
        return str(v) if v is not None else None
    
    @field_validator("album", mode='before')
    def validate_album(cls, v):
        """Convert empty album object to None."""
        if v is None:
            return None
        if isinstance(v, dict) and not v:  # Empty dict
            return None
        return v


class Playlist(BaseModel):
    """Playlist model."""
    uuid: str
    title: str
    description: Optional[str] = None
    numberOfTracks: Optional[int] = None
    numberOfVideos: Optional[int] = None
    duration: Optional[int] = None
    creator: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    
    @field_validator("uuid", mode='before')
    def validate_uuid(cls, v):
        """Convert integer UUID to string."""
        return str(v) if v is not None else None


class StreamUrl(BaseModel):
    """Stream URL model for audio tracks."""
    trackid: str
    soundQuality: str
    codec: Optional[str] = None
    encryptionKey: Optional[str] = None
    url: str
    urls: List[str] = Field(default_factory=list)
    
    @field_validator("trackid", mode='before')
    def validate_trackid(cls, v):
        """Convert integer track ID to string."""
        return str(v) if v is not None else None


class VideoStreamUrl(BaseModel):
    """Stream URL model for videos."""
    videoid: str
    resolution: str
    resolutions: Optional[List[str]] = None
    m3u8Url: str
    codec: Optional[str] = None
    
    @field_validator("videoid", mode='before')
    def validate_videoid(cls, v):
        """Convert integer video ID to string."""
        return str(v) if v is not None else None


class SearchResult(BaseModel):
    """Model for search results."""
    artists: Optional[Dict[str, Any]] = None
    albums: Optional[Dict[str, Any]] = None
    tracks: Optional[Dict[str, Any]] = None
    videos: Optional[Dict[str, Any]] = None
    playlists: Optional[Dict[str, Any]] = None


class Lyrics(BaseModel):
    """Lyrics model."""
    trackId: str
    subtitles: Optional[str] = None
    isrc: Optional[str] = None
    
    @field_validator("trackId", mode='before')
    def validate_track_id(cls, v):
        """Convert integer track ID to string."""
        return str(v) if v is not None else None


class LoginKey(BaseModel):
    """Login key model for authentication."""
    deviceCode: Optional[str] = None
    userCode: Optional[str] = None
    verificationUrl: Optional[str] = None
    authCheckTimeout: Optional[int] = None
    authCheckInterval: Optional[int] = None
    userId: Optional[str] = None
    countryCode: Optional[str] = None
    accessToken: Optional[str] = None
    refreshToken: Optional[str] = None
    expiresIn: Optional[int] = None
