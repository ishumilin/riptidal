"""
API package for RIPTIDAL.

This package provides classes and functions for interacting with the Tidal API.
"""

from riptidal.api.client import TidalClient, TidalError, AuthenticationError, APIError, ConnectionError
from riptidal.api.auth import AuthManager
from riptidal.api.models import (
    ResourceType, StreamQuality, Artist, Album, Track, Video, Playlist,
    StreamUrl, VideoStreamUrl, SearchResult, Lyrics, LoginKey
)

__all__ = [
    'TidalClient',
    'TidalError',
    'AuthenticationError',
    'APIError',
    'ConnectionError',
    'AuthManager',
    'ResourceType',
    'StreamQuality',
    'Artist',
    'Album',
    'Track',
    'Video',
    'Playlist',
    'StreamUrl',
    'VideoStreamUrl',
    'SearchResult',
    'Lyrics',
    'LoginKey',
]
