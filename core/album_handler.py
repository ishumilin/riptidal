"""
Handles album-specific fetching and metadata preparation for downloads.
"""
from typing import List, Dict, Any, Optional, Set

from riptidal.api.client import TidalClient
from riptidal.api.models import Album, Track
from riptidal.utils.logger import get_logger

class AlbumHandler:
    """
    Handles fetching album details and its tracks, and preparing metadata
    for album track downloads.
    """
    def __init__(self, client: TidalClient):
        self.client = client
        self.logger = get_logger(__name__)

    async def get_album_details_and_tracks(self, album_id: str) -> Optional[Album]:
        """
        Fetches full album details, including its list of tracks.
        Each track in the returned album object will have its `album` attribute
        set to this album.
        """
        self.logger.info(f"Fetching details and tracks for album ID: {album_id}")
        try:
            album = await self.client.get_album(album_id)
            if not album:
                self.logger.warning(f"Album {album_id} not found by API.")
                return None

            # Fetch tracks for this album
            # Assuming client.get_album_tracks returns a list of Track objects
            # or that album.tracks is populated by client.get_album
            album_tracks = await self.client.get_album_tracks(album_id)
            if not album_tracks:
                 self.logger.warning(f"No tracks found for album {album.title} (ID: {album_id}).")
                 album.tracks = []
            
            processed_tracks = []
            for track_data in album_tracks:
                track_data.album = album 
                processed_tracks.append(track_data)
            
            album.tracks = processed_tracks
            
            self.logger.info(f"Successfully fetched album '{album.title}' with {len(album.tracks)} tracks.")
            return album
        except Exception as e:
            self.logger.error(f"Error fetching album {album_id} details and tracks: {e}", exc_info=True)
            return None

    def prepare_album_track_metadata(
        self,
        album: Album, # Album object, presumably with album.tracks populated
        album_index: Optional[int],
        total_albums: Optional[int],
        original_track_ids: Set[str],
        original_total_tracks: Optional[int] = None,
        initial_completed_count: Optional[int] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Prepares a dictionary of metadata for each track in an album.
        
        Args:
            album: Album object with tracks
            album_index: Index of this album in the batch
            total_albums: Total number of albums in the batch
            original_track_ids: Set of original track IDs
            original_total_tracks: Original total track count before filtering
            initial_completed_count: Number of tracks already completed when starting album download
        """
        track_metadata_map: Dict[str, Dict[str, Any]] = {}
        if not album or not hasattr(album, 'tracks') or not album.tracks:
            self.logger.warning(f"Album '{album.title if album else 'Unknown'}' has no tracks to prepare metadata for.")
            return track_metadata_map

        # Use original total tracks if provided, otherwise use current track count
        total_tracks = original_total_tracks if original_total_tracks is not None else len(album.tracks)

        for i, track in enumerate(album.tracks):
            track_id_str = str(track.id)
            is_original = track_id_str in original_track_ids
            
            metadata = {
                'track_index': i + 1, # 1-based index within this album
                'total_tracks': total_tracks, # Total tracks in the original album
                'album_index': album_index,
                'total_albums': total_albums,
                'is_album_track': True,
                'album_title': album.title,
                'is_original': is_original,
                'album_initial_completed': initial_completed_count
            }
            track_metadata_map[track_id_str] = metadata
            self.logger.debug(f"Prepared metadata for album track {track_id_str} ('{track.title}'): {metadata}")
        return track_metadata_map
