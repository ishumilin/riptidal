"""
Library upgrade handler for RIPTIDAL.

This module handles the UI and coordination for upgrading
an existing music library to higher quality versions from Tidal.
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from riptidal.api.client import TidalClient
from riptidal.api.musicbrainz_client import MusicBrainzClient, MusicBrainzRecording
from riptidal.api.models import Track, StreamQuality
from riptidal.core.library_scanner import LibraryScanner, LibraryTrack
from riptidal.core.downloader import BatchDownloader
from riptidal.core.settings import Settings
from riptidal.core.track_manager import TrackManager
from riptidal.ui.progress_display import RichProgressManager
from riptidal.ui.input_utils import get_input, get_yes_no, get_choice
from riptidal.utils.logger import get_logger


class TrackMatch:
    """Represents a match between a library track and a Tidal track."""
    
    def __init__(
        self,
        library_track: LibraryTrack,
        tidal_track: Optional[Track] = None,
        musicbrainz_recording: Optional[MusicBrainzRecording] = None,
        match_confidence: float = 0.0,
        match_method: str = "unknown"
    ):
        self.library_track = library_track
        self.tidal_track = tidal_track
        self.musicbrainz_recording = musicbrainz_recording
        self.match_confidence = match_confidence
        self.match_method = match_method  # "isrc", "musicbrainz", "metadata"
        self.skip = False
        self.skip_reason = ""
    
    @property
    def is_matched(self) -> bool:
        """Check if a Tidal track was found."""
        return self.tidal_track is not None
    
    @property
    def needs_upgrade(self) -> bool:
        """Check if the track needs an upgrade."""
        if not self.is_matched or self.skip:
            return False
        
        # For now, always upgrade unless it's already FLAC
        # In the future, we could compare actual quality
        if self.library_track.format and 'flac' in self.library_track.format.lower():
            return False
        
        return True


class LibraryUpgradeHandler:
    """
    Handler for library upgrade operations.
    
    This class coordinates scanning, matching, and upgrading
    tracks from an existing music library.
    """
    
    def __init__(
        self,
        client: TidalClient,
        settings: Settings,
        track_manager: TrackManager,
        batch_downloader: BatchDownloader,
        progress_manager: RichProgressManager
    ):
        """Initialize the library upgrade handler."""
        self.client = client
        self.settings = settings
        self.track_manager = track_manager
        self.batch_downloader = batch_downloader
        self.progress_manager = progress_manager
        self.logger = get_logger(__name__)
        
        self.scanner = LibraryScanner()
        self.musicbrainz_client = MusicBrainzClient()
    
    async def handle_library_upgrade(self) -> None:
        """Main entry point for library upgrade functionality."""
        self.progress_manager.stop_display()
        
        print("\n=== Library Upgrade ===")
        print("This feature will scan your existing music library and upgrade tracks to higher quality versions from Tidal.")
        print()
        
        # Get library path
        default_path = Path.cwd() / "library"
        library_path_str = await get_input(
            f"Enter library path to scan [{default_path}]: ",
            default=str(default_path)
        )
        library_path = Path(library_path_str)
        
        if not library_path.exists():
            print(f"Error: Path does not exist: {library_path}")
            return
        
        if not library_path.is_dir():
            print(f"Error: Path is not a directory: {library_path}")
            return
        
        # Scan library
        print(f"\nScanning library: {library_path}")
        self.progress_manager.start_display("Scanning library...")
        
        try:
            tracks = await self.scanner.scan_directory(library_path)
        finally:
            self.progress_manager.stop_display()
        
        if not tracks:
            print("No audio files found in the library.")
            return
        
        # Show statistics
        stats = self.scanner.get_statistics(tracks)
        print(f"\nLibrary Statistics:")
        print(f"  Total tracks: {stats['total_tracks']}")
        print(f"  Total albums: {stats['total_albums']}")
        print(f"  Total size: {stats['total_size_mb']:.1f} MB")
        print(f"  Formats: {', '.join(f'{fmt}: {count}' for fmt, count in stats['formats'].items())}")
        print(f"  Tracks with ISRC: {stats['tracks_with_isrc']}")
        print(f"  Tracks with MusicBrainz ID: {stats['tracks_with_musicbrainz']}")
        
        if not await get_yes_no("\nProceed with track identification?", True):
            return
        
        try:
            # Match tracks
            print("\nIdentifying tracks...")
            matches = await self._match_tracks(tracks)
            
            # Show match results
            matched_count = sum(1 for m in matches if m.is_matched)
            upgrade_count = sum(1 for m in matches if m.needs_upgrade)
            
            print(f"\nMatching Results:")
            print(f"  Tracks matched: {matched_count}/{len(tracks)}")
            print(f"  Tracks needing upgrade: {upgrade_count}")
            
            if upgrade_count == 0:
                print("\nNo tracks need upgrading.")
                return
            
            # Review matches
            if await get_yes_no("\nReview matches before downloading?", True):
                await self._review_matches(matches)
            
            # Filter to tracks that need upgrade
            tracks_to_upgrade = [m for m in matches if m.needs_upgrade and not m.skip]
            
            if not tracks_to_upgrade:
                print("\nNo tracks selected for upgrade.")
                return
            
            print(f"\nReady to upgrade {len(tracks_to_upgrade)} tracks.")
            
            # Ask about file handling
            replace_files = await get_yes_no("Replace original files? (No = keep both)", False)
            
            if not await get_yes_no(f"Download {len(tracks_to_upgrade)} tracks?", True):
                return
            
            # Download tracks
            await self._download_upgrades(tracks_to_upgrade, replace_files)
        finally:
            # Ensure all client sessions are closed
            if self.musicbrainz_client.session:
                self.logger.debug("Closing MusicBrainz client session")
                await self.musicbrainz_client.session.close()
                self.musicbrainz_client.session = None
            
            # Also close the Tidal client session if it exists
            if self.client.session:
                self.logger.debug("Closing Tidal client session")
                await self.client.session.close()
                self.client.session = None
    
    async def _match_tracks(self, tracks: List[LibraryTrack]) -> List[TrackMatch]:
        """
        Match library tracks to Tidal tracks.
        
        Args:
            tracks: List of library tracks
            
        Returns:
            List of TrackMatch objects
        """
        matches = []
        
        self.progress_manager.start_display("Matching tracks...")
        self.progress_manager.set_batch_totals(len(tracks))
        
        # Initialize the MusicBrainz client session
        if self.musicbrainz_client.session is None:
            self.musicbrainz_client.session = self.musicbrainz_client._get_session()
            
        for i, track in enumerate(tracks):
            self.progress_manager.set_overall_progress_description(
                f"Matching track {i+1}/{len(tracks)}: {track.display_name}"
            )
            
            match = await self._match_single_track(track)
            matches.append(match)
            
            # Update progress
            if self.progress_manager.overall_task_id:
                self.progress_manager.overall_progress_display.update(
                    self.progress_manager.overall_task_id,
                    completed=i + 1
                )
                if self.progress_manager.live:
                    self.progress_manager.live.refresh()
        
        self.progress_manager.stop_display()
        return matches
    
    async def _match_single_track(self, track: LibraryTrack) -> TrackMatch:
        """
        Match a single library track to a Tidal track.
        
        Args:
            track: Library track to match
            
        Returns:
            TrackMatch object
        """
        # Try ISRC first if available
        if track.isrc:
            self.logger.info(f"Trying ISRC match for {track.display_name}: {track.isrc}")
            tidal_track = await self._search_tidal_by_isrc(track.isrc)
            if tidal_track:
                return TrackMatch(
                    library_track=track,
                    tidal_track=tidal_track,
                    match_confidence=1.0,
                    match_method="isrc"
                )
        
        # Try MusicBrainz if we have metadata
        if track.artist and track.title:
            self.logger.info(f"Searching MusicBrainz for {track.display_name}")
            
            # Search MusicBrainz
            mb_recordings = await self.musicbrainz_client.search_recordings(
                artist=track.artist,
                title=track.title,
                album=track.album,
                duration=track.duration_ms
            )
            
            if mb_recordings:
                # Score and sort recordings
                scored_recordings = []
                for recording in mb_recordings:
                    score = self.musicbrainz_client.calculate_match_score(
                        recording,
                        artist=track.artist,
                        title=track.title,
                        album=track.album,
                        duration=track.duration_ms
                    )
                    scored_recordings.append((score, recording))
                
                scored_recordings.sort(key=lambda x: x[0], reverse=True)
                
                # Try the best match
                best_score, best_recording = scored_recordings[0]
                
                if best_score >= 0.7:  # Good enough match
                    # Debug log the artist names
                    self.logger.debug(f"MusicBrainz artist_names: {best_recording.artist_names}")
                    self.logger.debug(f"MusicBrainz artist_credit: {best_recording.artist_credit}")
                    
                    # Try to find on Tidal using MusicBrainz data
                    artist_name = best_recording.artist_names
                    if artist_name == "Unknown Artist" and track.artist:
                        # Fallback to the original track artist if MusicBrainz returns "Unknown Artist"
                        self.logger.warning(f"MusicBrainz returned 'Unknown Artist', falling back to original artist: {track.artist}")
                        artist_name = track.artist
                    
                    tidal_track = await self._search_tidal_by_metadata(
                        artist=artist_name,
                        title=best_recording.title,
                        album=best_recording.first_release_title
                    )
                    
                    if tidal_track:
                        return TrackMatch(
                            library_track=track,
                            tidal_track=tidal_track,
                            musicbrainz_recording=best_recording,
                            match_confidence=best_score,
                            match_method="musicbrainz"
                        )
        
        # Try direct Tidal search
        if track.artist and track.title:
            self.logger.info(f"Searching Tidal directly for {track.display_name}")
            tidal_track = await self._search_tidal_by_metadata(
                artist=track.artist,
                title=track.title,
                album=track.album
            )
            
            if tidal_track:
                return TrackMatch(
                    library_track=track,
                    tidal_track=tidal_track,
                    match_confidence=0.5,  # Lower confidence for direct match
                    match_method="metadata"
                )
        
        # No match found
        return TrackMatch(library_track=track)
    
    async def _search_tidal_by_isrc(self, isrc: str) -> Optional[Track]:
        """Search Tidal for a track by ISRC."""
        try:
            # Search for the ISRC
            search_results = await self.client.search(
                query=isrc,
                types=['track'],
                limit=10
            )
            
            if search_results and search_results.tracks:
                tracks = search_results.tracks.get('items', [])
                
                # Look for exact ISRC match
                for track_data in tracks:
                    track = self.client._parse_model(track_data, Track)
                    if track.isrc == isrc:
                        return track
                
                # If no exact match, return first result
                if tracks:
                    return self.client._parse_model(tracks[0], Track)
            
        except Exception as e:
            self.logger.error(f"Error searching Tidal by ISRC {isrc}: {str(e)}")
        
        return None
    
    async def _search_tidal_by_metadata(
        self,
        artist: str,
        title: str,
        album: Optional[str] = None
    ) -> Optional[Track]:
        """Search Tidal for a track by metadata using multiple strategies."""
        # Define search strategies in order of preference
        search_strategies = [
            # Strategy 1: Artist + Title + Album (original strategy)
            lambda: self._try_search(f'{artist} {title} {album}' if album else f'{artist} {title}'),
            
            # Strategy 2: Artist + Title (without album)
            lambda: self._try_search(f'{artist} {title}'),
            
            # Strategy 3: "Artist - Title" format
            lambda: self._try_search(f'{artist} - {title}'),
            
            # Strategy 4: Title only (for very distinctive titles)
            lambda: self._try_search(title, min_score=0.5),  # Higher threshold for title-only
            
            # Strategy 5: Artist + partial title (first few words)
            lambda: self._try_search(f'{artist} {" ".join(title.split()[:2])}'),
            
            # Strategy 6: Quoted exact search
            lambda: self._try_search(f'"{artist}" "{title}"'),
            
            # Strategy 7: Artist in quotes, title without quotes
            lambda: self._try_search(f'"{artist}" {title}'),
            
            # Strategy 8: Title in quotes, artist without quotes
            lambda: self._try_search(f'{artist} "{title}"'),
            
            # Strategy 9: Remove special characters from title
            lambda: self._try_search(f'{artist} {self._clean_title(title)}'),
            
            # Strategy 10: Album + Title (for tracks with common names)
            lambda: self._try_search(f'{album} {title}', min_score=0.4) if album else None,
            
            # Strategy 11: Just the first word of the title with artist (for titles with subtitles)
            lambda: self._try_search(f'{artist} {title.split()[0]}', min_score=0.3) if len(title.split()) > 1 else None,
            
            # Strategy 12: Last resort - very low threshold with artist name
            lambda: self._try_search(f'{artist}', min_score=0.15)
        ]
        
        # Try each strategy until we find a match
        for strategy_index, strategy in enumerate(search_strategies):
            self.logger.debug(f"Trying search strategy #{strategy_index + 1}")
            result = await strategy()
            if result:
                self.logger.info(f"Found match using strategy #{strategy_index + 1}")
                return result
        
        self.logger.info(f"No matches found for {artist} - {title} after trying all search strategies")
        return None
    
    def _clean_title(self, title: str) -> str:
        """Remove special characters and parentheses from title."""
        # Remove content in parentheses, brackets, etc.
        import re
        cleaned = re.sub(r'\([^)]*\)', '', title)
        cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\{[^}]*\}', '', cleaned)
        
        # Remove special characters
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    async def _try_search(self, query: str, min_score: float = 0.2) -> Optional[Track]:
        """Try a single search query and score the results."""
        try:
            self.logger.debug(f"Searching Tidal with query: {query}")
            
            # Search for tracks
            search_results = await self.client.search(
                query=query,
                types=['track'],
                limit=20
            )
            
            if search_results and search_results.tracks:
                tracks = search_results.tracks.get('items', [])
                self.logger.debug(f"Found {len(tracks)} potential matches on Tidal")
                
                if not tracks:
                    return None
                
                # Extract artist and title from the query for scoring
                query_parts = query.replace('"', '').split()
                query_artist = query_parts[0] if query_parts else ""
                query_title = query_parts[-1] if len(query_parts) > 1 else ""
                
                # Score tracks
                scored_tracks = []
                
                for track_data in tracks:
                    track = self.client._parse_model(track_data, Track)
                    
                    # Calculate similarity score
                    score = 0.0
                    score_details = []
                    
                    # Artist match (more weight for exact match)
                    if any(a.lower() == query_artist.lower() for a in track.artist_names.split(', ')):
                        score += 0.4
                        score_details.append(f"Artist exact match: +0.4")
                    elif any(query_artist.lower() in a.lower() for a in track.artist_names.split(', ')):
                        score += 0.2
                        score_details.append(f"Artist partial match: +0.2")
                    elif any(a.lower() in query_artist.lower() for a in track.artist_names.split(', ')):
                        score += 0.1
                        score_details.append(f"Artist reverse partial match: +0.1")
                    
                    # Title match with word-by-word comparison for better fuzzy matching
                    query_title_words = set(w.lower() for w in query_title.split())
                    track_title_words = set(w.lower() for w in track.title.split())
                    
                    # Calculate word overlap
                    common_words = query_title_words.intersection(track_title_words)
                    if common_words:
                        word_match_score = len(common_words) / max(len(query_title_words), len(track_title_words))
                        score += word_match_score * 0.4  # Scale by max title score
                        score_details.append(f"Title word match ({len(common_words)}/{max(len(query_title_words), len(track_title_words))}): +{word_match_score * 0.4:.2f}")
                    
                    # Exact title match bonus
                    if track.title.lower() == query_title.lower():
                        score += 0.2
                        score_details.append(f"Title exact match bonus: +0.2")
                    
                    # Add bonus for high-confidence matches
                    if score >= 0.5:
                        score += 0.1
                        score_details.append(f"High confidence bonus: +0.1")
                    
                    # Add bonus for first result (Tidal's relevance ranking)
                    if len(scored_tracks) == 0:
                        score += 0.05
                        score_details.append(f"First result bonus: +0.05")
                    
                    scored_tracks.append((score, track, score_details))
                
                # Sort by score (highest first)
                scored_tracks.sort(key=lambda x: x[0], reverse=True)
                
                # Log all scored tracks for debugging
                for i, (score, track, details) in enumerate(scored_tracks[:3]):  # Log top 3 matches
                    self.logger.debug(f"Match #{i+1}: {track.artist_names} - {track.title} (Album: {track.album.title if track.album else 'Unknown'})")
                    self.logger.debug(f"  Score: {score:.2f} - {', '.join(details)}")
                
                # Get best match
                if scored_tracks:
                    best_score, best_track, _ = scored_tracks[0]
                    
                    # Use provided minimum score threshold
                    if best_score >= min_score:
                        self.logger.info(f"Found match with score {best_score:.2f}: {best_track.artist_names} - {best_track.title}")
                        return best_track
                    else:
                        self.logger.info(f"Best match score {best_score:.2f} below threshold ({min_score}): {best_track.artist_names} - {best_track.title}")
                else:
                    self.logger.info("No tracks found in search results")
            else:
                self.logger.info("No search results returned from Tidal")
            
        except Exception as e:
            self.logger.error(f"Error searching Tidal by metadata: {str(e)}")
        
        return None
    
    async def _review_matches(self, matches: List[TrackMatch]) -> None:
        """Allow user to review and modify matches."""
        print("\n=== Review Matches ===")
        
        for i, match in enumerate(matches):
            if not match.needs_upgrade:
                continue
            
            print(f"\n[{i+1}/{len(matches)}] Library: {match.library_track.display_name}")
            print(f"  Quality: {match.library_track.quality_info}")
            
            if match.is_matched:
                print(f"  Tidal: {match.tidal_track.artist_names} - {match.tidal_track.title}")
                if match.tidal_track.album:
                    print(f"  Album: {match.tidal_track.album.title}")
                print(f"  Match: {match.match_method} (confidence: {match.match_confidence:.0%})")
                
                choice = await get_choice(
                    "Action",
                    ["Accept", "Skip", "Search Again", "Skip All Remaining"],
                    default=0
                )
                
                if choice == 1:  # Skip
                    match.skip = True
                    match.skip_reason = "User skipped"
                elif choice == 2:  # Search Again
                    # TODO: Implement manual search
                    print("Manual search not yet implemented")
                elif choice == 3:  # Skip All
                    for remaining in matches[i:]:
                        if remaining.needs_upgrade:
                            remaining.skip = True
                            remaining.skip_reason = "User skipped all"
                    break
            else:
                print("  No match found on Tidal")
                
                if await get_yes_no("Skip this track?", True):
                    match.skip = True
                    match.skip_reason = "No match found"
    
    async def _download_upgrades(
        self,
        matches: List[TrackMatch],
        replace_files: bool
    ) -> None:
        """Download upgraded versions of tracks."""
        print(f"\nDownloading {len(matches)} tracks...")
        
        # Convert matches to Tidal tracks
        tracks_to_download = []
        track_to_match_map = {}
        
        for match in matches:
            if match.tidal_track:
                tracks_to_download.append(match.tidal_track)
                track_to_match_map[match.tidal_track.id] = match
        
        # Download tracks
        results = await self.batch_downloader.download_tracks(tracks_to_download)
        
        # Process results
        success_count = 0
        failed_count = 0
        
        for result in results:
            if result.success and not result.skipped:
                success_count += 1
                
                # Handle file replacement if requested
                if replace_files and result.track and result.track.id in track_to_match_map:
                    match = track_to_match_map[result.track.id]
                    old_file = match.library_track.file_path
                    
                    try:
                        # Create backup with .old extension
                        backup_path = old_file.with_suffix(old_file.suffix + '.old')
                        old_file.rename(backup_path)
                        self.logger.info(f"Backed up original file to: {backup_path}")
                        
                        # TODO: Move new file to original location
                        # This would require modifying the download path logic
                        
                    except Exception as e:
                        self.logger.error(f"Error handling file replacement: {str(e)}")
            else:
                failed_count += 1
        
        print(f"\nUpgrade complete!")
        print(f"  Successfully upgraded: {success_count}")
        print(f"  Failed: {failed_count}")
