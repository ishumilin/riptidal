"""
Pydantic models for download progress and results.
"""
import time
from pathlib import Path
from typing import Optional, List, Dict, Set, Union

from pydantic import BaseModel, Field
from riptidal.api.models import Track, Video # Import Video as well


class DownloadProgress(BaseModel):
    """Model for tracking download progress."""
    track_id: Optional[str] = None
    track_title: Optional[str] = None
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    artist_names_str: Optional[str] = None # For display in UI
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, downloading, completed, failed, skipped
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    track_index: Optional[int] = None  # Current track index in batch
    total_tracks: Optional[int] = None  # Total tracks in batch/current album
    video_index: Optional[int] = None  # Current video index in batch
    total_videos: Optional[int] = None  # Total videos in batch
    requested_quality: Optional[str] = None  # Requested quality
    actual_quality: Optional[str] = None  # Actual quality being downloaded
    album_title: Optional[str] = None  # Album title if part of album download
    album_index: Optional[int] = None  # Current album index in batch
    total_albums: Optional[int] = None  # Total albums in batch
    is_album_track: bool = False  # Whether this track is part of an album download
    is_original: bool = False  # Whether this track/video is from the original favorites/playlist
    is_video: bool = False  # Whether this is a video download
    album_initial_completed: Optional[int] = None  # Initial completed tracks when starting album download

    @property
    def progress_percentage(self) -> float:
        """Calculate the progress percentage."""
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Calculate the elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def speed(self) -> float:
        """Calculate the download speed in bytes per second."""
        if self.elapsed_time == 0:
            return 0.0
        return self.downloaded_bytes / self.elapsed_time


class DownloadResult(BaseModel):
    """Model for download results."""
    track: Optional[Track] = None  # Track object if this is a track download
    video: Optional[Video] = None  # Video object if this is a video download
    success: bool
    file_path: Optional[Path] = None
    error_message: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


class AlbumDownloadStatus(BaseModel):
    """Model for tracking album download status."""
    album_id: str
    album_title: str
    total_tracks: int
    downloaded_tracks: int = 0
    status: str = "in_progress"  # in_progress, completed, failed
    start_time: float = Field(default_factory=time.time)
    last_updated: float = Field(default_factory=time.time)
    track_ids: Set[str] = Field(default_factory=set)  # All track IDs in the album
    downloaded_track_ids: Set[str] = Field(default_factory=set)  # Track IDs that have been downloaded
    
    @property
    def progress_percentage(self) -> float:
        """Calculate the progress percentage."""
        if self.total_tracks == 0:
            return 0.0
        return (self.downloaded_tracks / self.total_tracks) * 100
    
    @property
    def remaining_track_ids(self) -> Set[str]:
        """Get the IDs of tracks that still need to be downloaded."""
        return self.track_ids - self.downloaded_track_ids
    
    @property
    def is_complete(self) -> bool:
        """Check if the album download is complete."""
        return self.downloaded_tracks >= self.total_tracks or self.status == "completed"
