"""
Handles video-related operations for RIPTIDAL.
"""
import asyncio
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

import aiofiles
import aiohttp

from riptidal.api.client import TidalClient
from riptidal.api.models import Video, Artist, VideoStreamUrl
from riptidal.core.settings import Settings, VideoQuality
from riptidal.utils.logger import get_logger
from riptidal.utils.paths import sanitize_filename


class VideoHandler:
    """
    Handles video-related operations.
    
    This class provides methods for fetching and preparing videos for download.
    """
    
    def __init__(self, client: TidalClient, settings: Settings):
        """
        Initialize the VideoHandler.
        
        Args:
            client: TidalClient instance
            settings: Settings instance
        """
        self.client = client
        self.settings = settings
        self.logger = get_logger(__name__)
    
    async def get_artist_videos(self, artist_id: str) -> List[Video]:
        """
        Get videos from an artist.
        
        Args:
            artist_id: Artist ID
            
        Returns:
            List of Video objects
        """
        self.logger.info(f"Fetching videos for artist {artist_id}")
        
        try:
            # Get artist details
            artist = await self.client.get_artist(artist_id)
            self.logger.info(f"Artist: {artist.name}")
            
            # Get videos
            videos = await self.client.get_artist_videos(artist_id)
            self.logger.info(f"Found {len(videos)} videos for artist {artist.name}")
            
            # Ensure all videos have the artist information
            for video in videos:
                if video.artist is None or video.artist.id is None:
                    video.artist = artist
            
            return videos
        except Exception as e:
            self.logger.error(f"Error fetching videos for artist {artist_id}: {str(e)}")
            raise
    
    async def get_favorite_artist_videos(self, artist_id: Optional[str] = None) -> Dict[Artist, List[Video]]:
        """
        Get videos from favorite artists.
        
        Args:
            artist_id: Optional artist ID to filter by
            
        Returns:
            Dictionary mapping artists to their videos
        """
        self.logger.info("Fetching videos from favorite artists")
        
        try:
            # Get favorite artists
            if artist_id:
                self.logger.info(f"Filtering by artist ID: {artist_id}")
                artists = [await self.client.get_artist(artist_id)]
            else:
                self.logger.info("Fetching all favorite artists")
                artists = await self.client.get_favorite_artists()
            
            self.logger.info(f"Found {len(artists)} artists")
            
            # Get videos for each artist
            result = {}
            for artist in artists:
                try:
                    videos = await self.get_artist_videos(artist.id)
                    if videos:
                        result[artist] = videos
                except Exception as e:
                    self.logger.error(f"Error fetching videos for artist {artist.name}: {str(e)}")
                    # Continue with next artist
            
            self.logger.info(f"Found videos for {len(result)} artists")
            return result
        except Exception as e:
            self.logger.error(f"Error fetching favorite artist videos: {str(e)}")
            raise
    
    async def get_favorite_videos(self) -> List[Video]:
        """
        Get favorite videos.
        
        Returns:
            List of Video objects
        """
        self.logger.info("Fetching favorite videos")
        
        try:
            videos = await self.client.get_favorite_videos()
            self.logger.info(f"Found {len(videos)} favorite videos")
            return videos
        except Exception as e:
            self.logger.error(f"Error fetching favorite videos: {str(e)}")
            raise
    
    def get_video_path(self, video: Video) -> Path:
        """
        Get the path for a video file.
        
        Args:
            video: Video object
            
        Returns:
            Path object for the video file
        """
        # Create base directory
        base_dir = Path(self.settings.download_path) / "Videos"
        
        # Create artist directory
        artist_name = video.artist.name if video.artist and video.artist.name else "Unknown Artist"
        artist_dir = base_dir / sanitize_filename(artist_name)
        
        # Create video filename
        # Videos don't have trackNumber, so we'll just use the title
        video_title = sanitize_filename(video.title)
        explicit_flag = " (Explicit)" if video.explicit else ""
        
        filename = f"{sanitize_filename(artist_name)} - {video_title}{explicit_flag}.mp4"
        
        return artist_dir / filename
    
    async def prepare_video_for_download(self, video: Video) -> Tuple[Video, VideoStreamUrl, Path]:
        """
        Prepare a video for download.
        
        Args:
            video: Video object
            
        Returns:
            Tuple of (Video, VideoStreamUrl, Path)
        """
        self.logger.info(f"Preparing video for download: {video.title}")
        
        try:
            # Get video stream URL
            stream_url = await self.client.get_video_stream_url(video.id, self.settings.video_quality)
            self.logger.info(f"Got stream URL with resolution: {stream_url.resolution}")
            
            # Get video path
            path = self.get_video_path(video)
            self.logger.info(f"Video will be saved to: {path}")
            
            # Create directory if it doesn't exist
            os.makedirs(path.parent, exist_ok=True)
            
            return video, stream_url, path
        except Exception as e:
            self.logger.error(f"Error preparing video for download: {str(e)}")
            raise
