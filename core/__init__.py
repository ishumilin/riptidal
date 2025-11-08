"""
Core package for RIPTIDAL.

This package provides core functionality for the application.
"""

from riptidal.core.settings import Settings, AudioQuality, VideoQuality, load_settings, save_settings
from riptidal.core.track_manager import TrackManager, LocalTrack
from riptidal.core.download_models import DownloadProgress, DownloadResult

__all__ = [
    'Settings',
    'AudioQuality',
    'VideoQuality',
    'load_settings',
    'save_settings',
    'TrackManager',
    'LocalTrack',
    'DownloadProgress',
    'DownloadResult',
]
