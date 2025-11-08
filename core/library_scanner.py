"""
Library scanner for RIPTIDAL.

This module provides functionality to scan a music library folder,
extract metadata from audio files, and prepare them for upgrade.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from riptidal.utils.logger import get_logger


@dataclass
class LibraryTrack:
    """Represents a track found in the library."""
    file_path: Path
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    duration_ms: Optional[int] = None
    bitrate: Optional[int] = None
    format: Optional[str] = None
    isrc: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    file_size: int = 0
    
    @property
    def quality_info(self) -> str:
        """Get a string representation of the track quality."""
        parts = []
        if self.format:
            parts.append(self.format.upper())
        if self.bitrate:
            parts.append(f"{self.bitrate}kbps")
        return " ".join(parts) if parts else "Unknown"
    
    @property
    def display_name(self) -> str:
        """Get a display name for the track."""
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        elif self.title:
            return self.title
        else:
            return self.file_path.name


class LibraryScanner:
    """
    Scanner for music library folders.
    
    This class scans directories for audio files and extracts
    their metadata for identification and upgrade.
    """
    
    # Supported audio file extensions
    SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.mp4', '.ogg', '.opus', '.wma'}
    
    def __init__(self):
        """Initialize the library scanner."""
        self.logger = get_logger(__name__)
        
        if not MUTAGEN_AVAILABLE:
            self.logger.warning("Mutagen library not available. Install with: pip install mutagen")
    
    async def scan_directory(self, directory: Path, recursive: bool = True) -> List[LibraryTrack]:
        """
        Scan a directory for audio files.
        
        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories
            
        Returns:
            List of LibraryTrack objects
        """
        if not directory.exists():
            self.logger.error(f"Directory does not exist: {directory}")
            return []
        
        if not directory.is_dir():
            self.logger.error(f"Path is not a directory: {directory}")
            return []
        
        self.logger.info(f"Scanning directory: {directory}")
        
        tracks = []
        
        if recursive:
            # Walk through all subdirectories
            for root, dirs, files in os.walk(directory):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                root_path = Path(root)
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_path = root_path / file
                    if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                        track = await self._extract_metadata(file_path)
                        if track:
                            tracks.append(track)
        else:
            # Only scan the top-level directory
            for file_path in directory.iterdir():
                if file_path.is_file() and not file_path.name.startswith('.'):
                    if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                        track = await self._extract_metadata(file_path)
                        if track:
                            tracks.append(track)
        
        self.logger.info(f"Found {len(tracks)} audio files in {directory}")
        return tracks
    
    async def _extract_metadata(self, file_path: Path) -> Optional[LibraryTrack]:
        """
        Extract metadata from an audio file.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            LibraryTrack object or None if extraction fails
        """
        try:
            # Get file size
            file_size = file_path.stat().st_size
            
            # Create basic track info
            track = LibraryTrack(
                file_path=file_path,
                file_size=file_size,
                format=file_path.suffix[1:].lower()
            )
            
            if not MUTAGEN_AVAILABLE:
                self.logger.debug(f"Cannot extract metadata without mutagen: {file_path}")
                return track
            
            # Extract metadata using mutagen
            audio_file = MutagenFile(str(file_path))
            
            if audio_file is None:
                self.logger.warning(f"Could not read audio file: {file_path}")
                return track
            
            # Extract common metadata
            track.artist = self._get_tag_value(audio_file, ['artist', 'TPE1', '\xa9ART'])
            track.title = self._get_tag_value(audio_file, ['title', 'TIT2', '\xa9nam'])
            track.album = self._get_tag_value(audio_file, ['album', 'TALB', '\xa9alb'])
            track.album_artist = self._get_tag_value(audio_file, ['albumartist', 'TPE2', 'aART'])
            
            # Extract track number
            track_num = self._get_tag_value(audio_file, ['tracknumber', 'TRCK', 'trkn'])
            if track_num:
                # Handle "1/12" format
                if isinstance(track_num, str) and '/' in track_num:
                    track_num = track_num.split('/')[0]
                try:
                    track.track_number = int(track_num)
                except (ValueError, TypeError):
                    pass
            
            # Extract ISRC
            track.isrc = self._get_tag_value(audio_file, ['isrc', 'TSRC'])
            
            # Extract MusicBrainz ID
            track.musicbrainz_id = self._get_tag_value(
                audio_file, 
                ['musicbrainz_trackid', 'TXXX:MusicBrainz Release Track Id']
            )
            
            # Extract duration
            if hasattr(audio_file.info, 'length') and audio_file.info.length:
                track.duration_ms = int(audio_file.info.length * 1000)
            
            # Extract bitrate
            if hasattr(audio_file.info, 'bitrate') and audio_file.info.bitrate:
                track.bitrate = audio_file.info.bitrate // 1000  # Convert to kbps
            
            # Special handling for FLAC
            if isinstance(audio_file, FLAC):
                track.format = 'flac'
                if hasattr(audio_file.info, 'bits_per_sample'):
                    bits = audio_file.info.bits_per_sample
                    sample_rate = audio_file.info.sample_rate
                    if bits and sample_rate:
                        track.format = f'flac {bits}bit/{sample_rate//1000}kHz'
            
            self.logger.debug(f"Extracted metadata for: {track.display_name}")
            return track
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {str(e)}")
            return LibraryTrack(file_path=file_path, file_size=file_path.stat().st_size)
    
    def _get_tag_value(self, audio_file: Any, tag_names: List[str]) -> Optional[str]:
        """
        Get a tag value from an audio file, trying multiple tag names.
        
        Args:
            audio_file: Mutagen audio file object
            tag_names: List of possible tag names to try
            
        Returns:
            Tag value as string or None
        """
        for tag_name in tag_names:
            try:
                if hasattr(audio_file, 'tags') and audio_file.tags:
                    value = audio_file.tags.get(tag_name)
                    if value:
                        # Handle list values
                        if isinstance(value, list) and value:
                            value = value[0]
                        # Convert to string
                        return str(value).strip()
                
                # Try direct attribute access
                if hasattr(audio_file, tag_name):
                    value = getattr(audio_file, tag_name)
                    if value:
                        if isinstance(value, list) and value:
                            value = value[0]
                        return str(value).strip()
                        
            except Exception:
                continue
        
        return None
    
    def group_by_album(self, tracks: List[LibraryTrack]) -> Dict[str, List[LibraryTrack]]:
        """
        Group tracks by album.
        
        Args:
            tracks: List of tracks to group
            
        Returns:
            Dictionary mapping album key to list of tracks
        """
        albums = {}
        
        for track in tracks:
            # Create album key
            album_artist = track.album_artist or track.artist or "Unknown Artist"
            album_name = track.album or "Unknown Album"
            album_key = f"{album_artist} - {album_name}"
            
            if album_key not in albums:
                albums[album_key] = []
            
            albums[album_key].append(track)
        
        # Sort tracks within each album by track number
        for album_tracks in albums.values():
            album_tracks.sort(key=lambda t: t.track_number or 999)
        
        return albums
    
    def get_statistics(self, tracks: List[LibraryTrack]) -> Dict[str, Any]:
        """
        Get statistics about the scanned tracks.
        
        Args:
            tracks: List of tracks
            
        Returns:
            Dictionary with statistics
        """
        total_size = sum(t.file_size for t in tracks)
        formats = {}
        
        for track in tracks:
            fmt = track.format or 'unknown'
            formats[fmt] = formats.get(fmt, 0) + 1
        
        albums = self.group_by_album(tracks)
        
        return {
            'total_tracks': len(tracks),
            'total_albums': len(albums),
            'total_size_mb': total_size / (1024 * 1024),
            'formats': formats,
            'tracks_with_isrc': sum(1 for t in tracks if t.isrc),
            'tracks_with_musicbrainz': sum(1 for t in tracks if t.musicbrainz_id)
        }
