"""
Download functionality for RIPTIDAL.

This module provides classes and functions for downloading tracks and videos from Tidal.
"""

import asyncio
import hashlib
import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Set, Union, Callable, Awaitable

import aiofiles
import aiohttp
from aiohttp import ClientTimeout

from riptidal.api.client import TidalClient, APIError, ConnectionError
from riptidal.api.models import Track, Album, Video, Artist, StreamUrl, VideoStreamUrl, StreamQuality, VideoQuality
from riptidal.core.settings import Settings
from riptidal.core.download_models import DownloadProgress, DownloadResult
from riptidal.core.album_handler import AlbumHandler # Import AlbumHandler
from riptidal.core.video_handler import VideoHandler # Import VideoHandler
from riptidal.utils.logger import get_logger
from riptidal.utils.paths import format_path, sanitize_filename


class TrackDownloader:
    """
    Class for downloading tracks from Tidal.
    
    This class handles downloading tracks, including checking for existing files,
    creating directories, and handling errors.
    """
    
    def __init__(
        self, 
        client: TidalClient, 
        settings: Settings,
        progress_callback: Optional[Callable[[DownloadProgress], Awaitable[None]]] = None,
        track_manager: Optional['TrackManager'] = None
    ):
        self.client = client
        self.settings = settings
        self.progress_callback = progress_callback
        self.logger = get_logger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._downloaded_tracks: Set[str] = set()
        self.track_manager = track_manager
        self._album_artist_cache: Dict[str, str] = {}
    
    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _get_track_path(self, track: Track, album: Optional[Album] = None) -> Path:
        album_name = "Unknown Album"
        if album and album.title:
            album_name = album.title
        elif track.album and track.album.title:
            album_name = track.album.title
        
        # Determine album ID for caching artist name
        album_id = None
        if album and album.id:
            album_id = album.id
        elif track.album and track.album.id:
            album_id = track.album.id
        
        if album_id:
            if album_id not in self._album_artist_cache:
                if album and album.artists:
                    artist_name = ", ".join(a.name for a in album.artists if a.name)
                    if not artist_name:
                        artist_name = track.artist_names
                elif track.album and hasattr(track.album, 'artists') and track.album.artists:
                    artist_name = ", ".join(a.name for a in track.album.artists if a.name)
                    if not artist_name:
                        artist_name = track.artist_names
                else:
                    artist_name = track.artist_names
                
                self._album_artist_cache[album_id] = artist_name
                self.logger.debug(f"Cached artist name for album {album_id}: {artist_name}")
            
            artist_name_for_path = self._album_artist_cache[album_id]
            self.logger.debug(f"Using cached artist name for album {album_id}: {artist_name_for_path}")
        else:
            artist_name_for_path = track.artist_names
            self.logger.debug(f"No album context, using track artists: {artist_name_for_path}")

        data = {
            "track_number": f"{track.trackNumber:02d}" if track.trackNumber else "00",
            "track_title": track.formatted_title,
            "artist_name": artist_name_for_path,
            "album_name": album_name,
            "album_year": album.release_year if album else (track.album.release_year if track.album else None),
            "explicit": "[E]" if track.explicit else "",
        }
        path = format_path(self.settings.track_path_format, data, self.settings.download_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.with_suffix(".flac") # Assuming FLAC for now, codec might change this
    
    async def _check_file_exists(self, path: Path) -> Tuple[bool, Optional[str]]:
        flac_path = path.with_suffix(".flac")
        m4a_path = path.with_suffix(".m4a")
        if flac_path.exists(): return True, f"File already exists: {flac_path.name}"
        if m4a_path.exists(): return True, f"File already exists: {m4a_path.name}"
        return False, None
    
    async def _download_file(self, url: str, path: Path, progress: DownloadProgress, retry_count: int = 0) -> bool:
        temp_path = path.with_suffix(path.suffix + ".part")
        try:
            progress.status = "downloading"
            progress.start_time = time.time()
            if self.progress_callback: await self.progress_callback(progress)
            
            session = self._get_session()
            # Use a timeout only for the initial connection, not for the entire download
            timeout = aiohttp.ClientTimeout(
                total=None,  # No total timeout - allow slow downloads to complete
                connect=30,  # 30 seconds to establish connection
                sock_connect=30,  # 30 seconds for socket connection
                sock_read=60  # 60 seconds of no data before timing out
            )
            
            async with session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    progress.status = "failed"; progress.error_message = f"HTTP error: {response.status}"
                    if self.progress_callback: await self.progress_callback(progress)
                    return False
                
                progress.total_bytes = int(response.headers.get("Content-Length", 0))
                async with aiofiles.open(temp_path, "wb") as f:
                    downloaded = 0
                    last_progress_time = time.time()
                    last_downloaded = 0
                    stall_timeout = 60  # Consider download stalled after 60 seconds of no progress
                    
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        progress.downloaded_bytes = downloaded
                        if self.progress_callback: await self.progress_callback(progress)
                        
                        # Check for stalled download
                        current_time = time.time()
                        if downloaded > last_downloaded:
                            last_progress_time = current_time
                            last_downloaded = downloaded
                        elif current_time - last_progress_time > stall_timeout:
                            raise asyncio.TimeoutError("Download stalled - no data received for 60 seconds")
            
            if temp_path.exists(): temp_path.rename(path)
            progress.status = "completed"
            if self.progress_callback: await self.progress_callback(progress)
            return True
        except asyncio.TimeoutError as e:
            error_msg = str(e) if str(e) else "Download timed out"
            self.logger.warning(f"{error_msg} for {path.name}")
            if retry_count < self.settings.retry_attempts:
                self.logger.info(f"Retrying download after timeout ({retry_count+1}/{self.settings.retry_attempts})")
                await asyncio.sleep(self.settings.retry_delay)
                return await self._download_file(url, path, progress, retry_count + 1)
            progress.status = "failed"; progress.error_message = f"{error_msg} after {self.settings.retry_attempts} retries"
            if self.progress_callback: await self.progress_callback(progress)
            return False
        except Exception as e:
            self.logger.exception(f"Download error: {e}")
            progress.status = "failed"; progress.error_message = str(e)
            if self.progress_callback: await self.progress_callback(progress)
            return False
        finally:
            progress.end_time = time.time()

    async def _check_track_availability(self, track_id: str) -> Tuple[bool, Optional[str]]:
        return True, None

    async def download_track(self, track: Track, album: Optional[Album] = None, progress_obj: Optional[DownloadProgress] = None) -> DownloadResult:
        path = self._get_track_path(track, album)
        # Index-only decision: skip if present in library index (ID, album status, ISRC, or metadata)
        if self.track_manager:
            try:
                is_present = await self.track_manager.is_track_in_library(track)
            except Exception:
                is_present = False
            if is_present:
                return DownloadResult(track=track, success=True, file_path=path, skipped=True, skip_reason="Already in library index")

        available, reason = await self._check_track_availability(track.id)
        if not available:
            return DownloadResult(track=track, success=True, skipped=True, skip_reason=reason)

        title = f"{track.formatted_title} - {track.artist_names}"
        if album and album.title: title += f" ({album.title})"
        
        progress = progress_obj or DownloadProgress(
            track_id=str(track.id),
            track_title=title,
            artist_names_str=track.artist_names
        )
        if not progress_obj:
            progress.track_index = getattr(track, 'track_index', None)
            progress.total_tracks = getattr(track, 'total_tracks', None)

        try:
            quality = StreamQuality(self.settings.audio_quality.value)
            progress.requested_quality = quality.name
            
            try:
                stream = await self.client.get_stream_url(track.id, quality)
                progress.actual_quality = stream.soundQuality
            except APIError as e:
                # Check if this is an "Asset is not ready for playback" error
                if hasattr(e, 'status_code') and e.status_code == 401:
                    if hasattr(e, 'sub_status') and e.sub_status == 4005:
                        self.logger.warning(f"Track {track.id} ({track.title}) is not ready for playback. Skipping.")
                        return DownloadResult(
                            track=track, 
                            success=True, 
                            skipped=True, 
                            skip_reason="Asset is not ready for playback"
                        )
                # Re-raise other API errors
                raise

            success = await self._download_file(stream.url, path, progress)
            if success:
                self._downloaded_tracks.add(track.id)
                if self.track_manager:
                    try:
                        self.logger.debug(f"Adding track {track.id} to index via TrackDownloader")
                        # Enrich with metadata we have at download time
                        album_id = getattr(album, "id", None) if album else (getattr(track.album, "id", None) if getattr(track, "album", None) else None)
                        album_title = getattr(album, "title", None) if album else (getattr(track.album, "title", None) if getattr(track, "album", None) else None)
                        await self.track_manager.add_track(
                            track.id,
                            path,
                            album_id=str(album_id) if album_id is not None else None,
                            album_title=album_title,
                            artist_names=getattr(track, "artist_names", None),
                            quality_requested=getattr(quality, "name", None),
                            quality_actual=getattr(stream, "soundQuality", None),
                            codec=getattr(stream, "codec", None),
                            track_title=getattr(track, "title", None),
                            isrc=getattr(track, "isrc", None),
                        )
                    except Exception as e:
                        self.logger.error(f"Error adding track {track.id} to index: {str(e)}", exc_info=True)
                return DownloadResult(track=track, success=True, file_path=path)
            return DownloadResult(track=track, success=False, error_message=progress.error_message or "Download failed")
        except Exception as e:
            return DownloadResult(track=track, success=False, error_message=str(e))


class VideoDownloader:
    """
    Class for downloading videos from Tidal.
    
    This class handles downloading videos, including checking for existing files,
    creating directories, and handling errors.
    """
    
    def __init__(
        self, 
        client: TidalClient, 
        settings: Settings,
        progress_callback: Optional[Callable[[DownloadProgress], Awaitable[None]]] = None
    ):
        self.client = client
        self.settings = settings
        self.progress_callback = progress_callback
        self.logger = get_logger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._downloaded_videos: Set[str] = set()
        self.video_handler = VideoHandler(client, settings)
    
    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _check_file_exists(self, path: Path) -> Tuple[bool, Optional[str]]:
        if path.exists():
            return True, f"File already exists: {path.name}"
        return False, None
    
    async def _download_m3u8(self, m3u8_url: str, output_path: Path, progress: DownloadProgress, retry_count: int = 0) -> bool:
        """
        Download a video from an M3U8 URL using ffmpeg.
        
        Args:
            m3u8_url: M3U8 URL
            output_path: Output path
            progress: Download progress object
            retry_count: Retry count
            
        Returns:
            True if successful, False otherwise
        """
        temp_path = output_path.with_suffix(output_path.suffix + ".part")
        try:
            progress.status = "downloading"
            progress.start_time = time.time()
            if self.progress_callback:
                await self.progress_callback(progress)
            
            # Create directory if it doesn't exist
            os.makedirs(output_path.parent, exist_ok=True)
            
            # Check if ffmpeg is installed
            try:
                # Use asyncio.create_subprocess_exec to run the command
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    self.logger.error("ffmpeg is not installed or not working properly")
                    progress.status = "failed"
                    progress.error_message = "ffmpeg is not installed or not working properly"
                    if self.progress_callback:
                        await self.progress_callback(progress)
                    return False
                
                self.logger.debug("ffmpeg is installed and working properly")
            except Exception as e:
                self.logger.error(f"Error checking ffmpeg: {e}")
                progress.status = "failed"
                progress.error_message = f"Error checking ffmpeg: {e}"
                if self.progress_callback:
                    await self.progress_callback(progress)
                return False
            
            # Use ffmpeg to download and process the M3U8 stream
            try:
                # Build the ffmpeg command
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-y",  # Overwrite output file if it exists
                    "-protocol_whitelist", "file,http,https,tcp,tls,crypto",  # Allow these protocols
                    "-i", m3u8_url,  # Input file
                    "-c", "copy",  # Copy streams without re-encoding
                    "-bsf:a", "aac_adtstoasc",  # Convert ADTS to ASC for AAC audio
                    "-f", "mp4",  # Output format
                    str(temp_path)  # Output file
                ]
                
                # Start the ffmpeg process
                process = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Set up progress monitoring with more realistic byte counts
                # Use 1MB as a unit to make the progress display look better
                progress.total_bytes = 100 * 1024 * 1024  # 100MB as placeholder total
                progress.downloaded_bytes = 0
                
                # Update progress immediately to show initial state
                if self.progress_callback:
                    await self.progress_callback(progress)
                
                # Set up a simple progress update task
                async def update_progress_periodically():
                    try:
                        # Update progress immediately to show initial state
                        if self.progress_callback:
                            await self.progress_callback(progress)
                        
                        # Monitor the ffmpeg process
                        while process.returncode is None:
                            # Update progress periodically
                            progress.downloaded_bytes += 1 * 1024 * 1024  # 1MB increment
                            
                            # Cap at 99% until complete
                            if progress.downloaded_bytes >= progress.total_bytes * 0.99:
                                progress.downloaded_bytes = int(progress.total_bytes * 0.99)
                            
                            if self.progress_callback:
                                await self.progress_callback(progress)
                            
                            # Check if process is still running
                            try:
                                process.returncode = process.poll()
                                if process.returncode is not None:
                                    break
                            except Exception:
                                pass
                            
                            # Wait a bit before updating again
                            await asyncio.sleep(0.2)
                    except Exception as e:
                        self.logger.error(f"Error in progress update task: {e}")
                
                # Start the progress update task
                progress_task = asyncio.create_task(update_progress_periodically())
                
                # Wait for the process to complete
                try:
                    stdout, stderr = await process.communicate()
                    
                    # Wait for the progress task to complete
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                except Exception as e:
                    self.logger.error(f"Error communicating with ffmpeg process: {e}")
                    progress_task.cancel()
                    try:
                        await progress_task
                    except asyncio.CancelledError:
                        pass
                    raise
                
                # Check if the process was successful
                if process.returncode != 0:
                    error_output = stderr.decode('utf-8', errors='ignore')
                    self.logger.error(f"ffmpeg error: {error_output}")
                    progress.status = "failed"
                    progress.error_message = f"ffmpeg error: {error_output[:200]}"
                    if self.progress_callback:
                        await self.progress_callback(progress)
                    return False
                
                # Set progress to 100%
                progress.downloaded_bytes = progress.total_bytes
                if self.progress_callback:
                    await self.progress_callback(progress)
                
            except Exception as e:
                self.logger.error(f"Error running ffmpeg: {e}")
                progress.status = "failed"
                progress.error_message = f"Error running ffmpeg: {e}"
                if self.progress_callback:
                    await self.progress_callback(progress)
                return False
            
            # Rename the temp file to the final file
            if temp_path.exists():
                temp_path.rename(output_path)
            
            progress.status = "completed"
            if self.progress_callback:
                await self.progress_callback(progress)
            
            return True
        except asyncio.TimeoutError:
            if retry_count < self.settings.retry_attempts:
                self.logger.info(f"Retrying download after timeout ({retry_count+1}/{self.settings.retry_attempts})")
                await asyncio.sleep(self.settings.retry_delay)
                return await self._download_m3u8(m3u8_url, output_path, progress, retry_count + 1)
            
            progress.status = "failed"
            progress.error_message = "Download timed out after retries"
            if self.progress_callback:
                await self.progress_callback(progress)
            
            return False
        except Exception as e:
            self.logger.exception(f"Download error: {e}")
            progress.status = "failed"
            progress.error_message = str(e)
            if self.progress_callback:
                await self.progress_callback(progress)
            
            return False
        finally:
            progress.end_time = time.time()
    
    async def download_video(self, video: Video, progress_obj: Optional[DownloadProgress] = None) -> DownloadResult:
        """
        Download a video.
        
        Args:
            video: Video object
            progress_obj: Optional progress object
            
        Returns:
            DownloadResult object
        """
        try:
            # Prepare video for download
            video, stream_url, path = await self.video_handler.prepare_video_for_download(video)
            
            # Check if file exists
            exists, reason = await self._check_file_exists(path)
            if exists:
                return DownloadResult(
                    track=None,
                    video=video,
                    success=True,
                    file_path=path,
                    skipped=True,
                    skip_reason=reason
                )
            
            # Create progress object if not provided
            title = f"{video.title} - {video.artist.name if video.artist else 'Unknown Artist'}"
            progress = progress_obj or DownloadProgress(
                video_id=str(video.id),
                video_title=title,
                artist_names_str=video.artist.name if video.artist else "Unknown Artist"
            )
            
            # Set video-specific progress fields
            progress.is_video = True
            progress.requested_quality = self.settings.video_quality.name
            progress.actual_quality = stream_url.resolution
            
            # Download the video
            success = await self._download_m3u8(stream_url.m3u8Url, path, progress)
            
            if success:
                self._downloaded_videos.add(video.id)
                return DownloadResult(
                    track=None,
                    video=video,
                    success=True,
                    file_path=path
                )
            
            return DownloadResult(
                track=None,
                video=video,
                success=False,
                error_message=progress.error_message or "Download failed"
            )
        except Exception as e:
            self.logger.error(f"Error downloading video {video.id}: {str(e)}", exc_info=True)
            return DownloadResult(
                track=None,
                video=video,
                success=False,
                error_message=str(e)
            )


class BatchDownloader:
    def __init__(
        self, 
        client: TidalClient, 
        settings: Settings, 
        progress_callback: Optional[Callable[[DownloadProgress], Awaitable[None]]] = None,
        track_manager: Optional['TrackManager'] = None
    ):
        self.client = client
        self.settings = settings
        self.progress_callback = progress_callback
        self.logger = get_logger(__name__)
        self.track_manager = track_manager
        self.downloader = TrackDownloader(client, settings, progress_callback, track_manager)
        self.video_downloader = VideoDownloader(client, settings, progress_callback)
        self.album_handler = AlbumHandler(client)
        self.video_handler = VideoHandler(client, settings)
        self._downloaded_track_ids: Set[str] = set()
        self._downloaded_video_ids: Set[str] = set()
        self._downloaded_album_ids: Set[str] = set()
        self._original_track_ids: Set[str] = set()
        self._original_video_ids: Set[str] = set()

    async def download_album(self, album_id: str, album_index: Optional[int] = None, total_albums: Optional[int] = None) -> List[DownloadResult]:
        self.logger.info(f"Starting download of album ID: {album_id}")
        try:
            try:
                album_obj = await self.album_handler.get_album_details_and_tracks(album_id)
            except Exception as e:
                # Check if this is a "Album not found" error
                if isinstance(e, APIError) and hasattr(e, 'status_code') and e.status_code == 404:
                    if hasattr(e, 'sub_status') and e.sub_status == 2001:
                        self.logger.error(f"Album {album_id} not found on Tidal (404). Removing from album status.")
                        if self.track_manager:
                            await self.track_manager.remove_album_status(album_id, reason="Album not found on Tidal (404)")
                        return []
                # Re-raise other exceptions
                raise

            if not album_obj or not hasattr(album_obj, 'tracks') or not album_obj.tracks:
                self.logger.warning(f"No tracks found for album {album_id} or album details incomplete.")
                if self.track_manager and album_id in self.track_manager.album_statuses:
                    await self.track_manager.remove_album_status(album_id, reason="No tracks found or album details incomplete")
                return []
            
            self.logger.info(f"Downloading album: {album_obj.title} with {len(album_obj.tracks)} tracks.")
        
            # Store the original total tracks before filtering
            original_total_tracks = len(album_obj.tracks)
            
            if self.track_manager:
                if not hasattr(self.track_manager, 'album_statuses') or not self.track_manager.album_statuses:
                    await self.track_manager.load_album_status()
                
                album_status = await self.track_manager.add_album_status(album_obj)
                
                # Check for tracks that were already downloaded individually (e.g., liked tracks)
                for track in album_obj.tracks:
                    track_id_str = str(track.id)
                    if track_id_str in self._downloaded_track_ids and track_id_str not in album_status.downloaded_track_ids:
                        await self.track_manager.update_album_track_status(album_obj.id, track_id_str, True)
                        self.logger.debug(f"Track {track_id_str} previously downloaded; updating album status (index-only, ignoring disk)")
                
                # Reload album status after updates
                album_status = self.track_manager.album_statuses.get(album_obj.id)
                
                if album_status.downloaded_tracks > 0:
                    self.logger.info(f"Resuming album download: '{album_obj.title}' ({album_status.downloaded_tracks}/{album_status.total_tracks} tracks already recorded in index)")
                    
                    remaining_tracks = [t for t in album_obj.tracks if str(t.id) not in album_status.downloaded_track_ids]
                    album_obj.tracks = remaining_tracks
                    
                    if not remaining_tracks:
                        self.logger.info(f"All tracks in album '{album_obj.title}' are present in the library index. Nothing to download.")
                        return []
                    
                    self.logger.info(f"Downloading {len(remaining_tracks)} remaining tracks from album '{album_obj.title}' (index-only, ignoring disk)")
            
            # Get the initial completed count from album status
            initial_completed_count = 0
            if self.track_manager and album_obj.id in self.track_manager.album_statuses:
                initial_completed_count = self.track_manager.album_statuses[album_obj.id].downloaded_tracks
            
            track_metadata = self.album_handler.prepare_album_track_metadata(
                album_obj, album_index, total_albums, self._original_track_ids, original_total_tracks, initial_completed_count
            )
            
            albums_map = {album_obj.id: album_obj}
            results = await self.download_tracks(
                album_obj.tracks, albums_map, is_album_download=True, track_metadata=track_metadata
            )
            
            if self.track_manager and hasattr(self.track_manager, 'album_statuses'):
                for result in results:
                    if result.success:  # Update status for all successful tracks, including skipped ones
                        await self.track_manager.update_album_track_status(album_obj.id, str(result.track.id), True)
            
            for result in results:
                if result.success and not result.skipped:
                    self._downloaded_track_ids.add(result.track.id)
            return results
        except Exception as e:
            self.logger.error(f"Error downloading album {album_id}: {str(e)}", exc_info=True)
            return []

    async def download_tracks(
        self, 
        tracks: List[Track], 
        albums: Optional[Dict[str, Album]] = None,
        is_album_download: bool = False,
        track_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        resume_incomplete_albums: str = "relevant",  # "none" | "relevant" | "all"
    ) -> List[DownloadResult]:
        try:
            if not is_album_download:
                self.logger.info(f"Starting batch download of {len(tracks)} tracks")
                self._original_track_ids = {str(t.id) for t in tracks}
                self.logger.debug(f"Stored {len(self._original_track_ids)} original track IDs.")

                if self.settings.download_full_albums:
                    self.logger.info("Full album download enabled, processing tracks in playlist order.")
                    all_results: List[DownloadResult] = []
                
                if self.track_manager:
                    await self.track_manager.load_album_status()
                    
                    all_album_ids = set(self.track_manager.album_statuses.keys())
                    
                    incomplete_albums = await self.track_manager.get_incomplete_albums()
                    incomplete_album_ids = {album.album_id for album in incomplete_albums}
                    
                    self._downloaded_album_ids = all_album_ids - incomplete_album_ids

                    # Determine which incomplete albums (if any) to resume
                    requested_album_ids: Set[str] = {
                        str(t.album.id)
                        for t in tracks
                        if getattr(t, "album", None) is not None and getattr(t.album, "id", None)
                    }
                    if resume_incomplete_albums == "none":
                        filtered_incomplete = []
                    elif resume_incomplete_albums == "relevant":
                        filtered_incomplete = [s for s in incomplete_albums if s.album_id in requested_album_ids]
                    else:
                        # "all"
                        filtered_incomplete = incomplete_albums

                    self.logger.info(
                        f"Initialized with {len(self._downloaded_album_ids)} completed albums. "
                        f"{len(filtered_incomplete)} incomplete albums will be resumed "
                        f"({resume_incomplete_albums})."
                    )
                    
                    if filtered_incomplete:
                        self.logger.info(f"Prioritizing {len(filtered_incomplete)} incomplete albums before processing individual tracks")
                        for album_status in filtered_incomplete:
                            self.logger.info(f"Resuming incomplete album: {album_status.album_title} ({album_status.downloaded_tracks}/{album_status.total_tracks} tracks)")
                            album_download_results = await self.download_album(album_status.album_id)
                            
                            if any(result.success and not result.skipped for result in album_download_results):
                                self._downloaded_album_ids.add(album_status.album_id)
                                self.logger.info(f"Marked album {album_status.album_id} as downloaded")
                            
                            all_results.extend(album_download_results)
                        
                        self.logger.info("Finished processing scoped incomplete albums, now processing individual tracks")
                
                # Calculate total unique albums for progress display
                unique_album_ids = {t.album.id for t in tracks if t.album and t.album.id}
                total_unique_albums = len(unique_album_ids)
                album_counter = 0
                processed_album_ids = set()
                
                for i, track in enumerate(tracks):
                    self.logger.info(f"Processing track {i+1}/{len(tracks)}: {track.title}")
                    
                    track_metadata_single = {
                        str(track.id): {'is_original': True, 'is_album_track': False}
                    }
                    track_results = await self._process_track_list([track], albums, track_metadata_single)
                    all_results.extend(track_results)
                    
                    if track.album and track.album.id and track.album.id not in self._downloaded_album_ids:
                        album_id_str = track.album.id
                        
                        # Increment album counter only for new albums
                        if album_id_str not in processed_album_ids:
                            album_counter += 1
                            processed_album_ids.add(album_id_str)
                        
                        is_incomplete = False
                        if self.track_manager and album_id_str in self.track_manager.album_statuses:
                            album_status = self.track_manager.album_statuses[album_id_str]
                            if album_status.status == "in_progress" and album_status.downloaded_tracks < album_status.total_tracks:
                                is_incomplete = True
                                self.logger.info(f"Resuming incomplete album: {album_status.album_title} ({album_status.downloaded_tracks}/{album_status.total_tracks} tracks)")
                        
                        if not is_incomplete:
                            self.logger.info(f"Downloading album for track: {track.title}")
                        
                        album_download_results = await self.download_album(
                            album_id_str, 
                            album_index=album_counter, 
                            total_albums=total_unique_albums
                        )
                        
                        if any(result.success and not result.skipped for result in album_download_results):
                            self._downloaded_album_ids.add(album_id_str)
                            self.logger.info(f"Marked album {album_id_str} as downloaded")
                        
                        all_results.extend(album_download_results)
                
                return all_results
            else:
                return await self._process_track_list(tracks, albums, track_metadata)
            
        except Exception as e:
            self.logger.error(f"Error downloading tracks: {str(e)}", exc_info=True)
            return []
        
        try:
            return await self._process_track_list(tracks, albums, track_metadata)
        except Exception as e:
            self.logger.error(f"Error processing album tracks: {str(e)}", exc_info=True)
            return []

    async def _process_track_list(
        self,
        tracks_to_process: List[Track],
        albums_context: Optional[Dict[str, Album]],
        metadata_map: Optional[Dict[str, Dict[str, Any]]]
    ) -> List[DownloadResult]:
        """Helper to process a list of tracks with semaphore and metadata."""
        results: List[DownloadResult] = []
        semaphore = asyncio.Semaphore(1)

        async def process_track(track: Track) -> DownloadResult:
            async with semaphore:
                if str(track.id) in self._downloaded_track_ids and (metadata_map and metadata_map.get(str(track.id), {}).get('is_album_track')):
                    self.logger.debug(f"Track {track.id} already processed as part of an album, skipping.")
                
                current_album_obj = None
                if track.album and track.album.id and albums_context:
                    current_album_obj = albums_context.get(track.album.id)

                progress = DownloadProgress(
                    track_id=str(track.id), 
                    track_title=track.formatted_title,
                    artist_names_str=track.artist_names
                )
                
                track_specific_meta = metadata_map.get(str(track.id)) if metadata_map else None
                if track_specific_meta:
                    progress.track_index = track_specific_meta.get('track_index')
                    progress.total_tracks = track_specific_meta.get('total_tracks')
                    progress.is_album_track = track_specific_meta.get('is_album_track', False)
                    progress.album_title = track_specific_meta.get('album_title')
                    progress.album_index = track_specific_meta.get('album_index')
                    progress.total_albums = track_specific_meta.get('total_albums')
                    progress.is_original = track_specific_meta.get('is_original', False)
                    progress.album_initial_completed = track_specific_meta.get('album_initial_completed')
                else: 
                    progress.is_original = str(track.id) in self._original_track_ids

                async with self.downloader:
                    result = await self.downloader.download_track(track, current_album_obj or track.album, progress_obj=progress)
                    if result.success and not result.skipped:
                        self._downloaded_track_ids.add(str(track.id))
                    return result

        for track in tracks_to_process:
            result = await process_track(track)
            results.append(result)
        
        return results

    async def download_videos(
        self,
        videos: List[Video],
        is_artist_videos: bool = False
    ) -> List[DownloadResult]:
        """
        Download a list of videos.
        
        Args:
            videos: List of Video objects
            is_artist_videos: Whether these are artist videos
            
        Returns:
            List of DownloadResult objects
        """
        self.logger.info(f"Starting batch download of {len(videos)} videos")
        
        if is_artist_videos:
            self._original_video_ids = {str(v.id) for v in videos}
            self.logger.debug(f"Stored {len(self._original_video_ids)} original video IDs.")
        
        results: List[DownloadResult] = []
        semaphore = asyncio.Semaphore(1)
        
        async def process_video(video: Video, index: int) -> DownloadResult:
            async with semaphore:
                if str(video.id) in self._downloaded_video_ids:
                    self.logger.debug(f"Video {video.id} already processed, skipping.")
                    return DownloadResult(
                        track=None,
                        video=video,
                        success=True,
                        skipped=True,
                        skip_reason="Already downloaded"
                    )
                
                progress = DownloadProgress(
                    video_id=str(video.id),
                    video_title=video.title,
                    artist_names_str=video.artist.name if video.artist else "Unknown Artist",
                    is_video=True
                )
                
                progress.video_index = index + 1
                progress.total_videos = len(videos)
                progress.is_original = str(video.id) in self._original_video_ids
                
                async with self.video_downloader:
                    result = await self.video_downloader.download_video(video, progress_obj=progress)
                    if result.success and not result.skipped:
                        self._downloaded_video_ids.add(str(video.id))
                    return result
        
        for i, video in enumerate(videos):
            result = await process_video(video, i)
            results.append(result)
        
        return results
    
    async def download_favorite_videos(self) -> List[DownloadResult]:
        """
        Download favorite videos.
        
        Returns:
            List of DownloadResult objects
        """
        self.logger.info("Starting download of favorite videos")
        
        try:
            favorite_videos = await self.video_handler.get_favorite_videos()
            if not favorite_videos:
                self.logger.info("No favorite videos found")
                return []
            
            self.logger.info(f"Found {len(favorite_videos)} favorite videos")
            return await self.download_videos(favorite_videos)
        except Exception as e:
            self.logger.error(f"Error downloading favorite videos: {str(e)}", exc_info=True)
            return []
    
    async def download_artist_videos(self, artist_id: str) -> List[DownloadResult]:
        """
        Download videos from an artist.
        
        Args:
            artist_id: Artist ID
            
        Returns:
            List of DownloadResult objects
        """
        self.logger.info(f"Starting download of videos for artist {artist_id}")
        
        try:
            artist_videos = await self.video_handler.get_artist_videos(artist_id)
            if not artist_videos:
                self.logger.info(f"No videos found for artist {artist_id}")
                return []
            
            self.logger.info(f"Found {len(artist_videos)} videos for artist {artist_id}")
            return await self.download_videos(artist_videos, is_artist_videos=True)
        except Exception as e:
            self.logger.error(f"Error downloading artist videos: {str(e)}", exc_info=True)
            return []
    
    async def download_favorite_artist_videos(self, artist_id: Optional[str] = None) -> List[DownloadResult]:
        """
        Download videos from favorite artists.
        
        Args:
            artist_id: Optional artist ID to filter by
            
        Returns:
            List of DownloadResult objects
        """
        self.logger.info("Starting download of videos from favorite artists")
        
        try:
            # Get videos from favorite artists
            artist_videos_map = await self.video_handler.get_favorite_artist_videos(artist_id)
            if not artist_videos_map:
                self.logger.info("No videos found for favorite artists")
                return []
            
            # Flatten the videos list
            all_videos = []
            for artist, videos in artist_videos_map.items():
                self.logger.info(f"Found {len(videos)} videos for artist {artist.name}")
                all_videos.extend(videos)
            
            self.logger.info(f"Found {len(all_videos)} videos from favorite artists")
            return await self.download_videos(all_videos, is_artist_videos=True)
        except Exception as e:
            self.logger.error(f"Error downloading favorite artist videos: {str(e)}", exc_info=True)
            return []
    
    async def download_favorite_tracks(self) -> List[DownloadResult]:
        self.logger.info("Starting download of favorite tracks")
        favorite_tracks = await self.client.get_favorite_tracks()
        if not favorite_tracks:
            self.logger.info("No favorite tracks found")
            return []
        self.logger.info(f"Found {len(favorite_tracks)} favorite tracks")
        
        albums_data = {}
        if self.settings.download_full_albums:
            album_ids = {t.album.id for t in favorite_tracks if t.album and t.album.id}
            for album_id in album_ids:
                album_detail = await self.album_handler.get_album_details_and_tracks(album_id)
                if album_detail:
                    albums_data[album_id] = album_detail
        
        return await self.download_tracks(favorite_tracks, albums=albums_data)
