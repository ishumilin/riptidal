"""
Handles download-related actions for the CLI.
"""
import os
from typing import TYPE_CHECKING, List, Optional
from pathlib import Path

from riptidal.api.client import TidalClient
from riptidal.api.models import Track, Album, Artist, Video
from riptidal.core.download_models import DownloadResult
from riptidal.core.settings import Settings
from riptidal.core.track_manager import TrackManager
from riptidal.ui.input_utils import get_yes_no
from riptidal.utils.logger import get_logger
from riptidal.utils.paths import sanitize_filename

if TYPE_CHECKING:
    from riptidal.api.auth import AuthManager
    from riptidal.ui.progress_display import RichProgressManager
    from riptidal.core.downloader import BatchDownloader # Ensure BatchDownloader is available for type hint

class DownloadHandler:
    def __init__(
        self,
        settings: Settings,
        client: TidalClient,
        auth_manager: 'AuthManager',
        track_manager: TrackManager,
        batch_downloader: 'BatchDownloader',
        progress_manager: 'RichProgressManager'
    ):
        self.settings = settings
        self.client = client
        self.auth_manager = auth_manager
        self.track_manager = track_manager
        if batch_downloader is None:
            self.batch_downloader = BatchDownloader(
                client,
                settings,
                progress_manager.update_progress if progress_manager else None,
                track_manager
            )
        else:
            if not hasattr(batch_downloader, 'track_manager') or batch_downloader.track_manager is None:
                batch_downloader.track_manager = track_manager
                if hasattr(batch_downloader, 'downloader'):
                    batch_downloader.downloader.track_manager = track_manager
            self.batch_downloader = batch_downloader
        self.progress_manager = progress_manager
        self.logger = get_logger(__name__)
        
        self._incomplete_albums_loaded = False

    def _get_track_path(self, track: Track, album: Optional[Album] = None) -> Path:
        """
        Get the expected path for a track.
        This uses the same logic as TrackDownloader._get_track_path to ensure consistency.
        """
        album_name = "Unknown Album"
        if album and album.title:
            album_name = album.title
        elif track.album and track.album.title:
            album_name = track.album.title
        
        artist_name_for_path = track.artist_names
        
        data = {
            "track_number": f"{track.trackNumber:02d}" if track.trackNumber else "00",
            "track_title": track.title,
            "artist_name": artist_name_for_path,
            "album_name": album_name,
            "album_year": album.release_year if album else (track.album.release_year if track.album else None),
            "explicit": "[E]" if track.explicit else "",
        }
        
        from riptidal.utils.paths import format_path
        path = format_path(self.settings.track_path_format, data, self.settings.download_path)
        return path.with_suffix(".flac")  # Assuming FLAC for now
    
    async def create_complete_m3u_playlist(self, name: str, tracks: List[Track]) -> None:
        """
        Creates a complete M3U playlist file with all tracks (both existing and to-be-downloaded).
        This is called at the beginning of the download process.
        """
        if not self.settings.create_m3u_playlists:
            return
        
        if not tracks:
            self.logger.warning(f"No tracks to include in M3U playlist '{name}'")
            return
        
        playlist_dir = self.settings.download_path / "Playlists"
        playlist_dir.mkdir(parents=True, exist_ok=True)
        playlist_file = playlist_dir / f"{sanitize_filename(name)}.m3u"
        
        try:
            with open(playlist_file, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                
                for track in tracks:
                    # Check if track is already downloaded
                    exists, path = await self.track_manager.check_track_exists(track.id)
                    
                    if not exists:
                        # Track not downloaded yet, use predicted path
                        path = self._get_track_path(track, track.album)
                    
                    # Use relative path in the M3U file
                    rel_path = os.path.relpath(path, self.settings.download_path)
                    artist = track.artist_names or "Unknown Artist"
                    title = track.title or "Unknown Title"
                    duration = track.duration or 0
                    
                    f.write(f"#EXTINF:{duration},{artist} - {title}\n")
                    f.write(f"{rel_path}\n")
            
            self.logger.info(f"Created complete M3U playlist: {playlist_file}")
            print(f"Created complete M3U playlist: {playlist_file}")
        except Exception as e:
            self.logger.error(f"Error creating complete M3U playlist '{name}': {e}")
            print(f"Error creating complete M3U playlist '{name}': {e}")
    
    async def create_m3u_playlist(self, name: str, tracks: List[Track], results: List[DownloadResult]) -> None:
        """
        Updates an M3U playlist file with newly downloaded tracks.
        This is called at the end of the download process.
        """
        # We now create the complete playlist at the beginning, so this is a no-op
        # Keeping the method for backward compatibility
        pass

    async def _print_missing_summary_for_tracks(self, label: str, tracks: List[Track]) -> None:
        """
        Print an optimized summary of missing tracks (up to 10 sample entries).
        """
        try:
            if hasattr(self.track_manager, "get_missing_for_tracks"):
                total, missing, sample = await self.track_manager.get_missing_for_tracks(tracks)
            else:
                # Fallback using compare_tracks
                new_tracks, existing_tracks = await self.track_manager.compare_tracks(tracks)
                total = len(tracks)
                missing = len(new_tracks)
                sample = new_tracks[:10]
            
            if missing > 0:
                print(f"{label}: Missing {missing} of {total} tracks.")
                print("Sample of missing (up to 10):")
                for t in sample:
                    try:
                        artist = t.artist_names or "Unknown Artist"
                    except Exception:
                        artist = "Unknown Artist"
                    title = getattr(t, "title", None) or "Unknown Title"
                    album_title = "Unknown Album"
                    try:
                        if getattr(t, "album", None) and getattr(t.album, "title", None):
                            album_title = t.album.title
                    except Exception:
                        pass
                    print(f"  - {artist} — {title} [{album_title}]")
        except Exception as e:
            self.logger.error(f"Error printing missing summary for {label}: {e}", exc_info=True)

    async def _print_missing_summary_for_album(self, album: Album) -> int:
        """
        Print a missing summary for a specific album. Returns the missing count.
        """
        missing = 0
        try:
            if hasattr(self.track_manager, "get_missing_for_album"):
                total, missing, sample = await self.track_manager.get_missing_for_album(album)
            else:
                # Fallback: compute via compare_tracks on album tracks
                tracks = getattr(album, "tracks", []) or []
                new_tracks, _ = await self.track_manager.compare_tracks(tracks)
                total = len(tracks)
                missing = len(new_tracks)
                sample = new_tracks[:10]
            
            if missing == 0:
                print(f"All tracks in album '{album.title}' already downloaded.")
            else:
                print(f"Album '{album.title}': Missing {missing} of {total} tracks.")
                print("Sample of missing (up to 10):")
                for t in sample:
                    try:
                        artist = t.artist_names or "Unknown Artist"
                    except Exception:
                        artist = "Unknown Artist"
                    title = getattr(t, "title", None) or "Unknown Title"
                    print(f"  - {artist} — {title}")
        except Exception as e:
            self.logger.error(f"Error printing album missing summary for '{getattr(album, 'title', 'Unknown')}': {e}", exc_info=True)
        return missing

    async def handle_download_favorites(self) -> None:
        """Handles downloading favorite tracks."""
        self.progress_manager.stop_display()
        print("\n=== Download Favorite Tracks ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download favorite tracks.")
            return
        
        await self.track_manager.load_index()
        print("Fetching favorite tracks...")
        all_favorite_tracks = await self.client.get_favorite_tracks()
        
        if not all_favorite_tracks:
            print("No favorite tracks found.")
            return
        
        print(f"Found {len(all_favorite_tracks)} favorite tracks.")
        new_tracks, existing_tracks = await self.track_manager.compare_tracks(all_favorite_tracks)
        print(f"New tracks: {len(new_tracks)}")
        print(f"Existing tracks: {len(existing_tracks)}")
        # Show what's missing with a small sample
        await self._print_missing_summary_for_tracks("Favorites", all_favorite_tracks)
        
        if not new_tracks:
            print("No new tracks to download.")
            return
            
        current_setting_download_albums = self.settings.download_full_albums
        download_albums = await get_yes_no(
            "Download full albums for each track?", current_setting_download_albums
        )

        num_albums_to_download = 0
        if download_albums:
            album_ids = {track.album.id for track in new_tracks if track.album and track.album.id}
            num_albums_to_download = len(album_ids)
            print(f"Individual new tracks: {len(new_tracks)}")
            print(f"Associated unique new albums to download: {num_albums_to_download}")
        else:
            print(f"Individual new tracks to download: {len(new_tracks)}")

        current_setting_create_m3u = self.settings.create_m3u_playlists
        create_m3u = await get_yes_no(
            "Create M3U playlist file for Favorites?", current_setting_create_m3u
        )

        confirm_prompt = f"Download {len(new_tracks)} new tracks"
        if download_albums and num_albums_to_download > 0:
            confirm_prompt += f" and {num_albums_to_download} associated full albums"
        confirm_prompt += "?"
        
        if not await get_yes_no(confirm_prompt, True):
            return
            
        # Create M3U playlist at the beginning if requested
        if create_m3u:
            await self.create_complete_m3u_playlist("Favorites", all_favorite_tracks)

        self.progress_manager.reset_progress_state()
        self.progress_manager.set_batch_totals(len(new_tracks))
        self.progress_manager.set_overall_progress_description("Downloading Favorites")
        self.progress_manager.start_display("Starting favorite tracks download...")

        results = await self.batch_downloader.download_tracks(
            new_tracks,
            resume_incomplete_albums="relevant" if download_albums else "none"
        )
        
        self.progress_manager.stop_display()

        success = sum(1 for r in results if r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = sum(1 for r in results if not r.success and not r.skipped)
        
        print("\n=== Download Summary (Favorites) ===")
        print(f"Downloaded: {success}")
        print(f"Skipped: {skipped}")
        print(f"Failed: {failed}")
        
        self.logger.info(f"Download operation complete for favorites. Processing {len(results)} results for track index.")
        successful_downloads_fav = 0
        for result in results:
            if result.success and not result.skipped and result.file_path:
                successful_downloads_fav += 1
                self.logger.debug(f"Calling track_manager.add_track for favorite track ID: {result.track.id}, path: {result.file_path}")
                await self.track_manager.add_track(result.track.id, result.file_path)
        self.logger.info(f"Attempted to add {successful_downloads_fav} favorite tracks to index.")
        
        # Save unified library and report
        final_track_count = len(self.track_manager.local_tracks)
        await self.track_manager.save_index()
        size_bytes = self.track_manager.state_path.stat().st_size if self.track_manager.state_path.exists() else 0
        print(f"Unified library now has {final_track_count} tracks")
        print(f"Unified library file: {self.track_manager.state_path} (size: {size_bytes} bytes)")
        
        if create_m3u:
            await self.create_m3u_playlist("Favorites", all_favorite_tracks, results)
    
    async def handle_download_favorite_albums(self) -> None:
        """Handles downloading favorite albums."""
        from riptidal.ui.input_utils import get_input # Local import for this method only
        
        self.progress_manager.stop_display()
        print("\n=== Download Favorite Albums ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download favorite albums.")
            return
        
        await self.track_manager.load_index()
        print("Fetching favorite albums...")
        favorite_albums = await self.client.get_favorite_albums()
        
        if not favorite_albums:
            print("No favorite albums found.")
            return
        
        print(f"Found {len(favorite_albums)} favorite albums:")
        for i, album in enumerate(favorite_albums):
            print(f"{i+1}. {album.title}")
        
        print("A. Download All Albums")
        print("0. Back")
        
        choice_str = await get_input("Enter album number or 'A' for all")
        if not choice_str or choice_str == "0":
            return
        
        albums_to_process = []
        if choice_str.upper() == "A":
            albums_to_process.extend(favorite_albums)
            if not await get_yes_no(f"Download all {len(albums_to_process)} albums?", True):
                return
        else:
            try:
                idx = int(choice_str) - 1
                if 0 <= idx < len(favorite_albums):
                    albums_to_process.append(favorite_albums[idx])
                else:
                    print("Invalid album number.")
                    return
            except ValueError:
                    print("Invalid choice.")
                    return
        
        total_downloaded_all_albums = 0
        total_skipped_all_albums = 0
        total_failed_all_albums = 0
        
        for i, album_to_download in enumerate(albums_to_process):
            print(f"\n=== Processing Album {i+1}/{len(albums_to_process)}: {album_to_download.title} ===")
            
            # Check if album is already in progress
            is_incomplete = False
            if self.track_manager and album_to_download.id in self.track_manager.album_statuses:
                album_status = self.track_manager.album_statuses[album_to_download.id]
                if album_status.status == "in_progress" and album_status.downloaded_tracks < album_status.total_tracks:
                    is_incomplete = True
                    print(f"Resuming incomplete album: {album_status.album_title} ({album_status.downloaded_tracks}/{album_status.total_tracks} tracks)")
            
            # Get album details and tracks
            album_obj = await self.batch_downloader.album_handler.get_album_details_and_tracks(album_to_download.id)
            
            if not album_obj or not hasattr(album_obj, 'tracks') or not album_obj.tracks:
                print(f"No tracks found for album '{album_to_download.title}'. Skipping.")
                continue
            
            print(f"Found {len(album_obj.tracks)} tracks in album '{album_obj.title}'.")
            
            # Index-only filter using library index (ignore physical disk)
            try:
                new_tracks, _ = await self.track_manager.compare_tracks(album_obj.tracks)
            except Exception:
                # Fallback: if compare_tracks not available or fails, keep original list
                new_tracks = album_obj.tracks or []
            
            if not new_tracks:
                print(f"All tracks in album '{album_obj.title}' already recorded in library. Skipping.")
                continue
            
            album_obj.tracks = new_tracks
            
            # If album is incomplete, further ensure only missing per album status
            if is_incomplete:
                album_status = self.track_manager.album_statuses[album_to_download.id]
                remaining_tracks = [t for t in album_obj.tracks if str(t.id) not in album_status.downloaded_track_ids]
                
                if not remaining_tracks:
                    print(f"All tracks in album '{album_obj.title}' have already been marked downloaded in library index.")
                    continue
                
                print(f"Downloading {len(remaining_tracks)} remaining tracks from album '{album_obj.title}'")
                album_obj.tracks = remaining_tracks
            
            # Show missing summary for this album; skip if nothing missing
            missing_for_album = await self._print_missing_summary_for_album(album_obj)
            if missing_for_album == 0:
                continue

            # Confirm for this specific album if processing multiple
            if len(albums_to_process) > 1:
                confirm_text = f"Download album '{album_obj.title}' with {len(album_obj.tracks)} tracks?"
                if not await get_yes_no(confirm_text, True):
                    continue
            
            self.progress_manager.reset_progress_state()
            self.progress_manager.set_batch_totals(len(album_obj.tracks))
            self.progress_manager.set_overall_progress_description(f"Album: {album_obj.title[:25]}...")
            self.progress_manager.start_display(f"Starting download for album: {album_obj.title}...")
            
            # Download album
            albums_map = {album_obj.id: album_obj}
            track_metadata = self.batch_downloader.album_handler.prepare_album_track_metadata(
                album_obj, i+1, len(albums_to_process), set()
            )
            
            results = await self.batch_downloader.download_tracks(
                album_obj.tracks, albums_map, is_album_download=True, track_metadata=track_metadata
            )
            
            self.progress_manager.stop_display()
            
            success = sum(1 for r in results if r.success and not r.skipped)
            skipped = sum(1 for r in results if r.skipped)
            failed = sum(1 for r in results if not r.success and not r.skipped)
            
            total_downloaded_all_albums += success
            total_skipped_all_albums += skipped
            total_failed_all_albums += failed
            
            print(f"\n--- Summary for Album: {album_obj.title} ---")
            print(f"Downloaded: {success}")
            print(f"Skipped: {skipped}")
            print(f"Failed: {failed}")
            
            # Update album status
            for result in results:
                if result.success and not result.skipped and result.file_path:
                    self.logger.debug(f"Calling track_manager.add_track for album track ID: {result.track.id}, path: {result.file_path}")
                    await self.track_manager.add_track(result.track.id, result.file_path)
                    
                    # Update album status
                    if album_obj.id in self.track_manager.album_statuses:
                        await self.track_manager.update_album_track_status(album_obj.id, str(result.track.id), True)
        
        if len(albums_to_process) > 1:
            print("\n=== Overall Download Summary (All Processed Albums) ===")
            print(f"Total Albums Processed: {len(albums_to_process)}")
            print(f"Total Downloaded: {total_downloaded_all_albums}")
            print(f"Total Skipped: {total_skipped_all_albums}")
            print(f"Total Failed: {total_failed_all_albums}")
    
    async def handle_download_favorite_artists(self) -> None:
        """Handles downloading albums from favorite artists."""
        from riptidal.ui.input_utils import get_input # Local import for this method only
        
        self.progress_manager.stop_display()
        print("\n=== Download Favorite Artists ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download favorite artists.")
            return
        
        await self.track_manager.load_index()
        print("Fetching favorite artists...")
        favorite_artists = await self.client.get_favorite_artists()
        
        if not favorite_artists:
            print("No favorite artists found.")
            return
        
        print(f"Found {len(favorite_artists)} favorite artists:")
        for i, artist in enumerate(favorite_artists):
            print(f"{i+1}. {artist.name}")
        
        print("A. Download All Artists")
        print("0. Back")
        
        choice_str = await get_input("Enter artist number or 'A' for all")
        if not choice_str or choice_str == "0":
            return
        
        artists_to_process = []
        if choice_str.upper() == "A":
            artists_to_process.extend(favorite_artists)
            if not await get_yes_no(f"Download all {len(artists_to_process)} artists?", True):
                return
        else:
            try:
                idx = int(choice_str) - 1
                if 0 <= idx < len(favorite_artists):
                    artists_to_process.append(favorite_artists[idx])
                else:
                    print("Invalid artist number.")
                    return
            except ValueError:
                    print("Invalid choice.")
                    return
        
        include_eps = await get_yes_no("Include EPs and singles?", False)
        
        total_albums_processed = 0
        total_downloaded_all_artists = 0
        total_skipped_all_artists = 0
        total_failed_all_artists = 0
        
        for i, artist_to_download in enumerate(artists_to_process):
            print(f"\n=== Processing Artist {i+1}/{len(artists_to_process)}: {artist_to_download.name} ===")
            
            # Get artist's albums
            print(f"Fetching albums for artist: {artist_to_download.name}...")
            
            # First get main albums and optionally EPs/singles
            artist_albums = []
            try:
                # Get albums from the API
                albums_data = await self._get_artist_albums(artist_to_download.id)
                if albums_data:
                    artist_albums.extend(albums_data)
                
                # If include_eps is True, get EPs and singles regardless of albums being empty
                if include_eps:
                    print("Fetching EPs and singles...")
                    eps_data = await self._get_artist_eps(artist_to_download.id)
                    if eps_data:
                        artist_albums.extend(eps_data)
                
                # De-duplicate by album ID to avoid duplicates across categories
                if artist_albums:
                    unique = {}
                    for a in artist_albums:
                        try:
                            unique[str(a.id)] = a
                        except Exception:
                            unique[repr(a)] = a
                    artist_albums = list(unique.values())
                
                if not artist_albums:
                    print(f"No albums or EPs/singles found for artist '{artist_to_download.name}'. Skipping.")
                    continue
                
                print(f"Found {len(artist_albums)} albums/EPs for artist '{artist_to_download.name}'.")
                
                # Display albums
                for j, album in enumerate(artist_albums):
                    print(f"  {j+1}. {album.title}")
                
                # Skip confirmation when downloading all artists (more than one artist)
                # Only confirm when downloading a single artist
                if len(artists_to_process) == 1:
                    confirm_text = f"Download {len(artist_albums)} albums from artist '{artist_to_download.name}'?"
                    if not await get_yes_no(confirm_text, True):
                        continue
                
                # Process each album
                for j, album in enumerate(artist_albums):
                    print(f"\n--- Processing Album {j+1}/{len(artist_albums)}: {album.title} ---")
                    
                    # Check if album is already in progress
                    is_incomplete = False
                    if self.track_manager and album.id in self.track_manager.album_statuses:
                        album_status = self.track_manager.album_statuses[album.id]
                        if album_status.status == "in_progress" and album_status.downloaded_tracks < album_status.total_tracks:
                            is_incomplete = True
                            print(f"Resuming incomplete album: {album_status.album_title} ({album_status.downloaded_tracks}/{album_status.total_tracks} tracks)")
                    
                    # Get album details and tracks
                    album_obj = await self.batch_downloader.album_handler.get_album_details_and_tracks(album.id)
                    
                    if not album_obj or not hasattr(album_obj, 'tracks') or not album_obj.tracks:
                        print(f"No tracks found for album '{album.title}'. Skipping.")
                        continue
                    
                    print(f"Found {len(album_obj.tracks)} tracks in album '{album_obj.title}'.")
                    
                    # Index-only filter using library index (ignore physical disk)
                    try:
                        new_tracks, _ = await self.track_manager.compare_tracks(album_obj.tracks)
                    except Exception:
                        new_tracks = album_obj.tracks or []
                    
                    if not new_tracks:
                        print(f"All tracks in album '{album_obj.title}' already recorded in library. Skipping.")
                        continue
                    
                    album_obj.tracks = new_tracks
                    
                    # If album is incomplete, further ensure only missing per album status
                    if is_incomplete:
                        album_status = self.track_manager.album_statuses[album.id]
                        remaining_tracks = [t for t in album_obj.tracks if str(t.id) not in album_status.downloaded_track_ids]
                        
                        if not remaining_tracks:
                            print(f"All tracks in album '{album_obj.title}' have already been marked downloaded in library index.")
                            continue
                        
                        print(f"Downloading {len(remaining_tracks)} remaining tracks from album '{album_obj.title}'")
                        album_obj.tracks = remaining_tracks
                    
                    # Show missing summary for this album; skip if nothing missing
                    missing_for_album = await self._print_missing_summary_for_album(album_obj)
                    if missing_for_album == 0:
                        continue

                    # Skip individual album confirmation when downloading all albums from a single artist
                    # Only confirm if we're processing a single artist with multiple albums
                    if len(artists_to_process) == 1 and len(artist_albums) > 1 and j > 0:
                        # Skip confirmation for subsequent albums (j > 0) when downloading all albums from a single artist
                        pass
                    elif len(artists_to_process) == 1 and len(artist_albums) > 1 and j == 0:
                        # Only confirm once for the first album when downloading all albums from a single artist
                        confirm_text = f"Download all {len(artist_albums)} albums from artist '{artist_to_download.name}'?"
                        if not await get_yes_no(confirm_text, True):
                            break  # Skip all albums from this artist
                    
                    self.progress_manager.reset_progress_state()
                    self.progress_manager.set_batch_totals(len(album_obj.tracks))
                    self.progress_manager.set_overall_progress_description(f"Album: {album_obj.title[:25]}...")
                    self.progress_manager.start_display(f"Starting download for album: {album_obj.title}...")
                    
                    # Download album
                    albums_map = {album_obj.id: album_obj}
                    track_metadata = self.batch_downloader.album_handler.prepare_album_track_metadata(
                        album_obj, j+1, len(artist_albums), set()
                    )
                    
                    results = await self.batch_downloader.download_tracks(
                        album_obj.tracks, albums_map, is_album_download=True, track_metadata=track_metadata
                    )
                    
                    self.progress_manager.stop_display()
                    
                    success = sum(1 for r in results if r.success and not r.skipped)
                    skipped = sum(1 for r in results if r.skipped)
                    failed = sum(1 for r in results if not r.success and not r.skipped)
                    
                    total_downloaded_all_artists += success
                    total_skipped_all_artists += skipped
                    total_failed_all_artists += failed
                    total_albums_processed += 1
                    
                    print(f"\n--- Summary for Album: {album_obj.title} ---")
                    print(f"Downloaded: {success}")
                    print(f"Skipped: {skipped}")
                    print(f"Failed: {failed}")
                    
                    # Update album status
                    for result in results:
                        if result.success and not result.skipped and result.file_path:
                            self.logger.debug(f"Calling track_manager.add_track for album track ID: {result.track.id}, path: {result.file_path}")
                            await self.track_manager.add_track(result.track.id, result.file_path)
                            
                            # Update album status
                            if album_obj.id in self.track_manager.album_statuses:
                                await self.track_manager.update_album_track_status(album_obj.id, str(result.track.id), True)
            
            except Exception as e:
                self.logger.error(f"Error processing artist {artist_to_download.name}: {str(e)}", exc_info=True)
                print(f"Error processing artist {artist_to_download.name}: {str(e)}")
                continue
        
        if len(artists_to_process) > 1:
            print("\n=== Overall Download Summary (All Processed Artists) ===")
            print(f"Total Artists Processed: {len(artists_to_process)}")
            print(f"Total Albums Processed: {total_albums_processed}")
            print(f"Total Downloaded: {total_downloaded_all_artists}")
            print(f"Total Skipped: {total_skipped_all_artists}")
            print(f"Total Failed: {total_failed_all_artists}")
    
    async def _get_artist_albums(self, artist_id: str) -> List[Album]:
        """Get albums for an artist."""
        items = await self.client._get_items(f'artists/{artist_id}/albums')
        
        albums = []
        for item in items:
            try:
                album = self.client._parse_model(item, Album)
                albums.append(album)
            except Exception as e:
                self.logger.error(f"Error processing album: {str(e)}")
        
        return albums
    
    async def _get_artist_eps(self, artist_id: str) -> List[Album]:
        """Get EPs and singles for an artist."""
        items = await self.client._get_items(f'artists/{artist_id}/albums', {"filter": "EPSANDSINGLES"})
        
        eps = []
        for item in items:
            try:
                album = self.client._parse_model(item, Album)
                eps.append(album)
            except Exception as e:
                self.logger.error(f"Error processing EP/single: {str(e)}")
        
        return eps

    async def handle_download_playlist(self) -> None:
        """Handles downloading tracks from a playlist."""
        from riptidal.ui.input_utils import get_input # Local import for this method only

        self.progress_manager.stop_display()
        print("\n=== Download Playlist ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download playlists.")
            return
        
        if not self.settings.enable_playlists:
            print("Playlists are disabled in settings.")
            return
        
        await self.track_manager.load_index()
        print("Fetching user playlists...")
        user_playlists = await self.client.get_user_playlists()
        
        if not user_playlists:
            print("No playlists found.")
            return
        
        print(f"Found {len(user_playlists)} playlists:")
        for i, pl in enumerate(user_playlists):
            print(f"{i+1}. {pl.title} ({pl.numberOfTracks} tracks)")
        
        print("A. Download All Playlists")
        print("0. Back")
        
        choice_str = await get_input("Enter playlist number or 'A' for all")
        if not choice_str or choice_str == "0":
            return
        
        playlists_to_process = []
        if choice_str.upper() == "A":
            playlists_to_process.extend(user_playlists)
            if not await get_yes_no(f"Download all {len(playlists_to_process)} playlists?", True):
                return
        else:
            try:
                idx = int(choice_str) - 1
                if 0 <= idx < len(user_playlists):
                    playlists_to_process.append(user_playlists[idx])
                else:
                    print("Invalid playlist number.")
                    return
            except ValueError:
                    print("Invalid choice.")
                    return

        current_setting_download_albums = self.settings.download_full_albums
        download_albums_for_all = await get_yes_no(
            "Download full albums for tracks in selected playlist(s)?", current_setting_download_albums
        )
        
        current_setting_create_m3u = self.settings.create_m3u_playlists
        create_m3u_for_all = await get_yes_no(
            "Create M3U playlist file(s)?", current_setting_create_m3u
        )

        total_downloaded_all_playlists = 0
        total_skipped_all_playlists = 0
        total_failed_all_playlists = 0

        for i, playlist_to_download in enumerate(playlists_to_process):
            print(f"\n=== Processing Playlist {i+1}/{len(playlists_to_process)}: {playlist_to_download.title} ===")
            
            print(f"Fetching tracks for playlist '{playlist_to_download.title}'...")
            all_playlist_tracks = await self.client.get_playlist_tracks(playlist_to_download.uuid)
            
            if not all_playlist_tracks:
                print(f"No tracks found in playlist '{playlist_to_download.title}'. Skipping.")
                continue
            
            print(f"Found {len(all_playlist_tracks)} tracks.")
            new_tracks, existing_tracks = await self.track_manager.compare_tracks(all_playlist_tracks)
            print(f"New tracks to download: {len(new_tracks)}")
            print(f"Existing tracks: {len(existing_tracks)}")
            # Show what's missing with a small sample
            await self._print_missing_summary_for_tracks(f"Playlist '{playlist_to_download.title}'", all_playlist_tracks)
            
            if not new_tracks:
                print(f"No new tracks to download for playlist '{playlist_to_download.title}'. Skipping.")
                continue

            if len(playlists_to_process) > 1 or choice_str.upper() != "A":
                 num_albums_to_download_this_pl = 0
                 if download_albums_for_all:
                     album_ids_this_pl = {track.album.id for track in new_tracks if track.album and track.album.id}
                     num_albums_to_download_this_pl = len(album_ids_this_pl)
                 
                 confirm_text = f"Download {len(new_tracks)} new tracks"
                 if download_albums_for_all and num_albums_to_download_this_pl > 0:
                     confirm_text += f" and {num_albums_to_download_this_pl} associated albums"
                 confirm_text += f" from '{playlist_to_download.title}'?"
                 if not await get_yes_no(confirm_text, True):
                     continue # Skip this playlist

            # Create M3U playlist at the beginning if requested
            if create_m3u_for_all:
                await self.create_complete_m3u_playlist(playlist_to_download.title, all_playlist_tracks)

            self.progress_manager.reset_progress_state()
            self.progress_manager.set_batch_totals(len(new_tracks))
            self.progress_manager.set_overall_progress_description(f"Playlist: {playlist_to_download.title[:25]}...")
            self.progress_manager.start_display(f"Starting download for playlist: {playlist_to_download.title}...")

            results = await self.batch_downloader.download_tracks(
                new_tracks,
                resume_incomplete_albums="relevant" if download_albums_for_all else "none"
            )
            self.progress_manager.stop_display()

            success = sum(1 for r in results if r.success and not r.skipped)
            skipped = sum(1 for r in results if r.skipped)
            failed = sum(1 for r in results if not r.success and not r.skipped)
            
            total_downloaded_all_playlists += success
            total_skipped_all_playlists += skipped
            total_failed_all_playlists += failed

            print(f"\n--- Summary for Playlist: {playlist_to_download.title} ---")
            print(f"Downloaded: {success}")
            print(f"Skipped: {skipped}")
            print(f"Failed: {failed}")
            
            self.logger.debug(f"Processing {len(results)} results for playlist '{playlist_to_download.title}' for track index.")
            successful_playlist_tracks = 0
            for result in results:
                if result.success and not result.skipped and result.file_path:
                    successful_playlist_tracks +=1
                    self.logger.debug(f"Calling track_manager.add_track for playlist track ID: {result.track.id}, path: {result.file_path}")
                    await self.track_manager.add_track(result.track.id, result.file_path)
            self.logger.info(f"Attempted to add {successful_playlist_tracks} tracks from playlist '{playlist_to_download.title}' to index.")
            
            # Save unified library and report
            current_track_count = len(self.track_manager.local_tracks)
            await self.track_manager.save_index()
            size_bytes = self.track_manager.state_path.stat().st_size if self.track_manager.state_path.exists() else 0
            print(f"Unified library now has {current_track_count} tracks")
            print(f"Unified library file: {self.track_manager.state_path} (size: {size_bytes} bytes)")
            
            if create_m3u_for_all:
                await self.create_m3u_playlist(playlist_to_download.title, all_playlist_tracks, results)
        
        if len(playlists_to_process) > 1:
            print("\n=== Overall Download Summary (All Processed Playlists) ===")
            print(f"Total Playlists Processed: {len(playlists_to_process)}")
            print(f"Total Downloaded: {total_downloaded_all_playlists}")
            print(f"Total Skipped: {total_skipped_all_playlists}")
            print(f"Total Failed: {total_failed_all_playlists}")
    
    async def _load_incomplete_albums(self) -> List['AlbumDownloadStatus']:
        """Load incomplete album statuses."""
        if not self._incomplete_albums_loaded:
            await self.track_manager.load_album_status()
            self._incomplete_albums_loaded = True
        
        return await self.track_manager.get_incomplete_albums()
    
    async def handle_download_favorite_videos(self) -> None:
        """Handles downloading favorite videos."""
        self.progress_manager.stop_display()
        print("\n=== Download Favorite Videos ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download favorite videos.")
            return
        
        print("Fetching favorite videos...")
        
        try:
            favorite_videos = await self.batch_downloader.video_handler.get_favorite_videos()
            
            if not favorite_videos:
                print("No favorite videos found.")
                return
            
            print(f"Found {len(favorite_videos)} favorite videos.")
            
            # Confirm download
            if not await get_yes_no(f"Download {len(favorite_videos)} videos?", True):
                return
            
            self.progress_manager.reset_progress_state()
            self.progress_manager.set_batch_totals(len(favorite_videos))
            self.progress_manager.set_overall_progress_description("Downloading Favorite Videos")
            self.progress_manager.start_display("Starting favorite videos download...")
            
            results = await self.batch_downloader.download_videos(favorite_videos)
            
            self.progress_manager.stop_display()
            
            success = sum(1 for r in results if r.success and not r.skipped)
            skipped = sum(1 for r in results if r.skipped)
            failed = sum(1 for r in results if not r.success and not r.skipped)
            
            print("\n=== Download Summary (Favorite Videos) ===")
            print(f"Downloaded: {success}")
            print(f"Skipped: {skipped}")
            print(f"Failed: {failed}")
            
        except Exception as e:
            self.logger.error(f"Error downloading favorite videos: {str(e)}", exc_info=True)
            print(f"Error downloading favorite videos: {str(e)}")
    
    async def handle_download_favorite_artist_videos(self) -> None:
        """Handles downloading videos from favorite artists."""
        from riptidal.ui.input_utils import get_input # Local import for this method only
        
        self.progress_manager.stop_display()
        print("\n=== Download Favorite Artist Videos ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to download favorite artist videos.")
            return
        
        print("Fetching favorite artists...")
        favorite_artists = await self.client.get_favorite_artists()
        
        if not favorite_artists:
            print("No favorite artists found.")
            return
        
        print(f"Found {len(favorite_artists)} favorite artists:")
        for i, artist in enumerate(favorite_artists):
            print(f"{i+1}. {artist.name}")
        
        print("A. Download All Artists")
        print("0. Back")
        
        choice_str = await get_input("Enter artist number or 'A' for all")
        if not choice_str or choice_str == "0":
            return
        
        try:
            if choice_str.upper() == "A":
                if not await get_yes_no(f"Download videos from all {len(favorite_artists)} artists?", True):
                    return
                
                self.progress_manager.reset_progress_state()
                self.progress_manager.set_overall_progress_description("Downloading Favorite Artist Videos")
                self.progress_manager.start_display("Starting favorite artist videos download...")
                
                results = await self.batch_downloader.download_favorite_artist_videos()
                
                self.progress_manager.stop_display()
                
                success = sum(1 for r in results if r.success and not r.skipped)
                skipped = sum(1 for r in results if r.skipped)
                failed = sum(1 for r in results if not r.success and not r.skipped)
                
                print("\n=== Download Summary (All Favorite Artist Videos) ===")
                print(f"Downloaded: {success}")
                print(f"Skipped: {skipped}")
                print(f"Failed: {failed}")
                
            else:
                try:
                    idx = int(choice_str) - 1
                    if 0 <= idx < len(favorite_artists):
                        artist = favorite_artists[idx]
                        
                        print(f"Fetching videos for artist: {artist.name}...")
                        artist_videos = await self.batch_downloader.video_handler.get_artist_videos(artist.id)
                        
                        if not artist_videos:
                            print(f"No videos found for artist: {artist.name}")
                            return
                        
                        print(f"Found {len(artist_videos)} videos for artist: {artist.name}")
                        
                        if not await get_yes_no(f"Download {len(artist_videos)} videos from {artist.name}?", True):
                            return
                        
                        self.progress_manager.reset_progress_state()
                        self.progress_manager.set_batch_totals(len(artist_videos))
                        self.progress_manager.set_overall_progress_description(f"Downloading {artist.name} Videos")
                        self.progress_manager.start_display(f"Starting download for {artist.name} videos...")
                        
                        results = await self.batch_downloader.download_videos(artist_videos, is_artist_videos=True)
                        
                        self.progress_manager.stop_display()
                        
                        success = sum(1 for r in results if r.success and not r.skipped)
                        skipped = sum(1 for r in results if r.skipped)
                        failed = sum(1 for r in results if not r.success and not r.skipped)
                        
                        print(f"\n=== Download Summary ({artist.name} Videos) ===")
                        print(f"Downloaded: {success}")
                        print(f"Skipped: {skipped}")
                        print(f"Failed: {failed}")
                    else:
                        print("Invalid artist number.")
                except ValueError:
                    print("Invalid choice.")
        except Exception as e:
            self.logger.error(f"Error downloading favorite artist videos: {str(e)}", exc_info=True)
            print(f"Error downloading favorite artist videos: {str(e)}")

    async def handle_recreate_library_from_favorites(self) -> None:
        """Recreate unified library_state.json indexing all favorite tracks as if downloaded."""
        from riptidal.ui.input_utils import get_yes_no

        self.progress_manager.stop_display()
        print("\n=== Recreate Library From Favorites ===")

        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to recreate the library from favorites.")
            return

        state_path = self.track_manager.state_path
        print(f"This will replace the unified library file:\n  {state_path}")
        if not await get_yes_no("Proceed and replace the current unified library?", False):
            print("Operation cancelled.")
            return

        # Option to enrich album statuses with total_tracks and accurate downloaded sets
        fetch_album_details = await get_yes_no("Fetch album details for accurate album statuses?", True)
        delete_legacy = await get_yes_no("Delete legacy .data index files after recreation?", True)

        try:
            print("Fetching favorite tracks...")
            favorite_tracks = await self.client.get_favorite_tracks()
            if not favorite_tracks:
                print("No favorite tracks found.")
                return
            print(f"Found {len(favorite_tracks)} favorite tracks.")

            # Clear unified state (with backup)
            await self.track_manager.clear_all_indexes(backup=True)

            # Optionally prefetch album details
            albums_map = {}
            if fetch_album_details:
                album_ids = {t.album.id for t in favorite_tracks if t.album and t.album.id}
                print(f"Fetching details for {len(album_ids)} unique albums...")
                for aid in album_ids:
                    try:
                        album_obj = await self.batch_downloader.album_handler.get_album_details_and_tracks(aid)
                        if album_obj:
                            albums_map[aid] = album_obj
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch album {aid}: {e}")

            # Index all favorites as “downloaded”
            added = 0
            for tr in favorite_tracks:
                # Predict path using current format (index-only, no actual files created)
                predicted_path = self._get_track_path(tr, tr.album if hasattr(tr, "album") else None)
                album_id = getattr(tr.album, "id", None) if hasattr(tr, "album") and tr.album else None
                album_title = getattr(tr.album, "title", None) if hasattr(tr, "album") and tr.album else None

                await self.track_manager.add_track(
                    str(tr.id),
                    predicted_path,
                    album_id=str(album_id) if album_id else None,
                    album_title=album_title,
                    artist_names=getattr(tr, "artist_names", None),
                    track_title=getattr(tr, "title", None),
                    isrc=getattr(tr, "isrc", None),
                    quality_requested=self.settings.audio_quality.name,
                    source_favorites=True,
                    allow_missing_file=True,  # index-only
                )
                added += 1

            # Build album statuses if requested
            albums_built = 0
            if fetch_album_details and albums_map:
                # Aggregate favorites by album
                fav_by_album = {}
                for tr in favorite_tracks:
                    aid = getattr(tr.album, "id", None) if hasattr(tr, "album") and tr.album else None
                    if not aid:
                        continue
                    fav_by_album.setdefault(str(aid), set()).add(str(tr.id))

                for aid, album_obj in albums_map.items():
                    try:
                        status = await self.track_manager.add_album_status(album_obj)
                        # Mark favorite tracks from this album as downloaded
                        for tr_id in fav_by_album.get(str(aid), set()):
                            await self.track_manager.update_album_track_status(str(aid), tr_id, True)
                        albums_built += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to build album status for {aid}: {e}")

            # Save unified state
            await self.track_manager.save_index()
            await self.track_manager.save_album_status()

            if delete_legacy:
                await self.track_manager.delete_legacy_files()

            size_bytes = state_path.stat().st_size if state_path.exists() else 0
            print("\n=== Recreation Complete ===")
            print(f"Tracks indexed: {added}")
            if fetch_album_details:
                print(f"Albums processed: {albums_built}")
            print(f"Unified library saved: {state_path} ({size_bytes} bytes)")
        except Exception as e:
            self.logger.error(f"Error recreating library from favorites: {e}", exc_info=True)
            print(f"Error recreating library from favorites: {e}")
