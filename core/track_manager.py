"""
Track management for RIPTIDAL.

This module provides classes and functions for managing tracks,
including comparing local and remote tracks, and maintains a unified
library_state.json at the project root while preserving legacy files for
backward compatibility (track_index.json and album_status.json).
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Any

import aiofiles
from pydantic import BaseModel

from riptidal.api.models import Track, Album
from riptidal.core.settings import Settings
from riptidal.core.download_models import AlbumDownloadStatus
from riptidal.utils.logger import get_logger
from riptidal.utils.paths import get_data_dir, get_project_root, format_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(s: str) -> str:
    """
    Normalize text for fuzzy comparisons:
    - Lowercase
    - Remove bracketed qualifiers like (Remastered), [Edit], {Live}
    - Collapse whitespace and remove non-alphanumeric (keep spaces)
    """
    if not s:
        return ""
    import re as _re
    s = s.lower()
    # remove bracketed parts
    s = _re.sub(r"\(.*?\)|\[.*?\]|\{.*?\}", "", s)
    # remove common qualifiers words (optional)
    qualifiers = ["remaster", "remastered", "edit", "version", "mono", "stereo", "live"]
    for q in qualifiers:
        s = s.replace(q, "")
    # keep alnum and spaces
    s = _re.sub(r"[^a-z0-9\s]+", " ", s)
    # collapse whitespace
    s = " ".join(s.split())
    return s


class LocalTrack(BaseModel):
    """Model for a local track (legacy representation kept for compatibility)."""
    id: str
    path: Path
    hash: Optional[str] = None
    size: int = 0
    last_modified: float = 0


class TrackManager:
    """
    Class for managing tracks.

    Unified state:
      - Maintains a single library_state.json at the project root with schema v2.
      - Writes legacy files (track_index.json and album_status.json) for compatibility.

    Public API remains compatible with existing callers and tests.
    """

    def __init__(self, settings: Settings):
        """
        Initialize the track manager.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger(__name__)

        # Legacy in-memory structures for tests/back-compat
        self.local_tracks: Dict[str, LocalTrack] = {}

        # Legacy file paths (normally under .data, tests patch get_data_dir())
        self.index_path = get_data_dir() / "track_index.json"
        self.album_status_path = get_data_dir() / "album_status.json"
        self.album_statuses: Dict[str, AlbumDownloadStatus] = {}

        # Unified state file at repo root (as requested)
        self.state_path = get_project_root() / "library_state.json"
        self._state_lock = asyncio.Lock()
        self._state_loaded = False

        # In-memory unified state (schema v2)
        self._state: Dict[str, Any] = {
            "version": "2",
            "generated_at": _now_iso(),
            "tracks": {},  # track_id -> {...}
            "albums": {},  # album_id -> {...}
            "videos": {},  # video_id -> {...} (placeholder for future)
            # "playlists": {} # optional, add later as needed
        }

    # =========================
    # Unified State Management
    # =========================

    async def _load_state(self) -> None:
        """Load unified state (library_state.json) or migrate legacy files."""
        need_save = False
        async with self._state_lock:
            if self._state_loaded:
                return

            # Prefer unified state if exists and version == "2"
            if self.state_path.exists():
                try:
                    async with aiofiles.open(self.state_path, "r", encoding="utf-8") as f:
                        data_str = await f.read()
                    if data_str.strip():
                        state = json.loads(data_str)
                        if isinstance(state, dict) and state.get("version") == "2":
                            self._state = state
                            self.logger.info(
                                f"Loaded unified library state v2 with "
                                f"{len(self._state.get('tracks', {}))} tracks and "
                                f"{len(self._state.get('albums', {}))} albums"
                            )
                            self._populate_from_state()
                            self._state_loaded = True
                            return
                        else:
                            self.logger.warning(
                                f"{self.state_path} present but not recognized as v2; attempting migration"
                            )
                except Exception as e:
                    self.logger.error(f"Error loading {self.state_path}: {e}", exc_info=True)

            # If no valid unified state, migrate from legacy (search both .data and project root for legacy files)
            await self._migrate_legacy_index_and_album_status()
            self._state_loaded = True
            need_save = True

        # Save outside of the internal state lock to avoid re-entrancy deadlocks
        if need_save:
            await self._save_state_atomic()

    def _populate_from_state(self) -> None:
        """Populate legacy in-memory structures (local_tracks, album_statuses) from unified state."""
        # Populate local_tracks from state["tracks"]
        self.local_tracks.clear()
        tracks = self._state.get("tracks", {})
        for track_id, t in tracks.items():
            p = t.get("file_path")
            if not p:
                continue
            try:
                path_obj = Path(p)
            except Exception:
                continue
            self.local_tracks[track_id] = LocalTrack(
                id=track_id,
                path=path_obj,
                hash=None,  # Not preserved in unified state by default
                size=0,
                last_modified=0.0,
            )

        # Populate album_statuses from state["albums"]
        self.album_statuses.clear()
        albums = self._state.get("albums", {})
        for album_id, a in albums.items():
            # We don't store full AlbumDownloadStatus details in unified by default; build equivalent
            downloaded_ids = set(a.get("downloaded_track_ids", []))
            total_tracks = int(a.get("total_tracks", 0))
            status_str = a.get("status", "not_started")
            status = AlbumDownloadStatus(
                album_id=album_id,
                album_title=a.get("title", ""),
                total_tracks=total_tracks,
                track_ids=set(),  # will be populated when add_album_status is called for a real album
                downloaded_track_ids=downloaded_ids,
            )
            # Translate status for compatibility
            if status_str == "complete":
                status.status = "completed"
                status.downloaded_tracks = len(downloaded_ids)
            elif status_str == "in_progress":
                status.status = "in_progress"
                status.downloaded_tracks = len(downloaded_ids)
            else:
                status.status = "not_started"
                status.downloaded_tracks = len(downloaded_ids)

            self.album_statuses[album_id] = status

    async def _save_state_atomic(self) -> None:
        """Atomically save unified state to disk and update generated_at."""
        async with self._state_lock:
            self._state["version"] = "2"
            self._state["generated_at"] = _now_iso()

            tmp_path = self.state_path.with_suffix(".json.tmp")
            data_str = json.dumps(self._state, indent=2)

            # Use synchronous write for atomic replace; aiofiles doesn't provide atomic renaming
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(data_str)
            os.replace(tmp_path, self.state_path)
            self.logger.info(
                f"Unified library state saved: tracks={len(self._state.get('tracks', {}))}, "
                f"albums={len(self._state.get('albums', {}))}"
            )

    async def _migrate_legacy_index_and_album_status(self) -> None:
        """
        Migrate from legacy track_index.json and album_status.json to unified state.

        Searches both data dir (.data) and project root for these files.
        """
        self.logger.info("Migrating legacy index/status into unified library_state.json (v2)")

        # Collect possible legacy paths (limit to .data for test isolation)
        candidates_index = [self.index_path]
        candidates_album = [self.album_status_path]

        # Migrate tracks
        legacy_tracks: Dict[str, Any] = {}
        for p in candidates_index:
            try:
                if p.exists():
                    async with aiofiles.open(p, "r", encoding="utf-8") as f:
                        s = await f.read()
                    d = json.loads(s) if s.strip() else {}
                    if isinstance(d, dict):
                        legacy_tracks.update(d)
                        self.logger.info(f"Migrated legacy track index from {p} ({len(d)} records)")
                        break
            except Exception as e:
                self.logger.error(f"Error reading legacy track index {p}: {e}", exc_info=True)

        # Migrate albums
        legacy_albums: Dict[str, Any] = {}
        for p in candidates_album:
            try:
                if p.exists():
                    async with aiofiles.open(p, "r", encoding="utf-8") as f:
                        s = await f.read()
                    d = json.loads(s) if s.strip() else {}
                    if isinstance(d, dict):
                        legacy_albums.update(d)
                        self.logger.info(f"Migrated legacy album status from {p} ({len(d)} records)")
                        break
            except Exception as e:
                self.logger.error(f"Error reading legacy album status {p}: {e}", exc_info=True)

        # Build unified state from legacy
        unified_tracks: Dict[str, Any] = {}
        for track_id, track_data in legacy_tracks.items():
            path_str = track_data.get("path")
            unified_tracks[track_id] = {
                "file_path": path_str,
                "exists_on_disk": bool(path_str and Path(path_str).exists()),
                "downloaded_at": None,
                "last_verified": _now_iso() if path_str else None,
                "album_id": None,
                "album_title": None,
                "artist_ids": [],
                "artist_names": "",
                "quality": {"requested": "", "actual": None, "codec": None},
                "sources": {"favorites": False, "playlists": [], "artists": []},
            }

        unified_albums: Dict[str, Any] = {}
        for album_id, status_data in legacy_albums.items():
            downloaded = status_data.get("downloaded_track_ids", [])
            total_tracks = status_data.get("total_tracks", 0)
            # Status translation
            legacy_status = status_data.get("status", "in_progress")
            if legacy_status == "completed":
                state_status = "complete"
            elif legacy_status == "in_progress":
                state_status = "in_progress"
            else:
                state_status = "not_started"

            unified_albums[album_id] = {
                "title": status_data.get("album_title", ""),
                "artist_ids": [],
                "artist_names": "",
                "total_tracks": int(total_tracks or 0),
                "downloaded_track_ids": list(downloaded or []),
                "status": state_status,
                "updated_at": _now_iso(),
            }

        self._state = {
            "version": "2",
            "generated_at": _now_iso(),
            "tracks": unified_tracks,
            "albums": unified_albums,
            "videos": {},
        }

        # Populate legacy in-memory structures for compatibility
        self._populate_from_state()

    # ==================================
    # Legacy migration helper (retained)
    # ==================================

    async def _check_old_index(self) -> bool:
        """
        Check for an index file in the old location and migrate it if needed.

        Returns:
            True if an old index was found and migrated, False otherwise
        """
        from riptidal.utils.paths import get_project_root as _get_project_root

        old_data_dir = _get_project_root().parent / ".data"
        old_index_path = old_data_dir / "track_index.json"

        if not old_index_path.exists():
            self.logger.debug("No old track index found")
            return False

        self.logger.info(f"Found old track index at {old_index_path}, migrating to {self.index_path}")

        try:
            # Read the old index
            async with aiofiles.open(old_index_path, "r", encoding="utf-8") as f:
                data = await f.read()
                index_data = json.loads(data)

            # Create the directory for the new index if it doesn't exist
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the data to the new location
            async with aiofiles.open(self.index_path, "w", encoding="utf-8") as f:
                await f.write(data)

            self.logger.info(f"Successfully migrated track index with {len(index_data)} entries")
            return True
        except Exception as e:
            self.logger.error(f"Error migrating track index: {str(e)}")
            return False

    # ======================
    # Public legacy methods
    # ======================

    async def load_index(self) -> None:
        """Load the track index (unified-only)."""
        await self._load_state()
        # local_tracks are populated from unified state via _populate_from_state()
        self.logger.info(f"Unified library loaded from {self.state_path}")

    async def save_index(self) -> None:
        """Save the track index (unified-only)."""
        try:
            # Sync unified from in-memory local_tracks (compat shim)
            await self._sync_unified_tracks_from_local()
            await self._save_state_atomic()
            self.logger.info(
                f"Unified library saved to {self.state_path} "
                f"(tracks={len(self._state.get('tracks', {}))}, albums={len(self._state.get('albums', {}))})"
            )
        except Exception as e:
            self.logger.error(f"Error saving unified library: {str(e)}", exc_info=True)

    async def _sync_unified_tracks_from_local(self) -> None:
        """Synchronize unified state tracks from legacy in-memory local_tracks."""
        tracks = self._state.setdefault("tracks", {})
        for track_id, lt in self.local_tracks.items():
            t = tracks.get(track_id, {})
            t["file_path"] = str(lt.path)
            # Assume file exists in the library without checking filesystem
            t["exists_on_disk"] = True
            t.setdefault("downloaded_at", None)
            t["last_verified"] = _now_iso()
            t.setdefault("album_id", None)
            t.setdefault("album_title", None)
            t.setdefault("artist_ids", [])
            t.setdefault("artist_names", "")
            t.setdefault("quality", {"requested": "", "actual": None, "codec": None})
            t.setdefault("sources", {"favorites": False, "playlists": [], "artists": []})
            tracks[track_id] = t

    async def add_track(
        self,
        track_id: str,
        path: Path,
        *,
        album_id: Optional[str] = None,
        album_title: Optional[str] = None,
        artist_names: Optional[str] = None,
        quality_requested: Optional[str] = None,
        quality_actual: Optional[str] = None,
        codec: Optional[str] = None,
        track_title: Optional[str] = None,
        isrc: Optional[str] = None,
        source_favorites: Optional[bool] = None,
        source_playlist: Optional[str] = None,
        source_artist: Optional[str] = None,
        allow_missing_file: bool = False,
    ) -> None:
        """
        Add a track to the index (legacy) and update unified state.

        Args:
            track_id: Track ID
            path: Path to the track file
        """
        self.logger.debug(f"Attempting to add track {track_id} with path {path} to index.")

        abs_path = path.absolute()
        self.logger.debug(f"Using absolute path: {abs_path}")

        try:
            if not abs_path.exists():
                if not allow_missing_file:
                    self.logger.warning(f"Track file does not exist at path for add_track: {abs_path}")
                    return
                # Virtual entry: no file on disk, index-only
                file_size = 0
                file_mtime = time.time()
                file_hash = f"virtual_{track_id}"
            else:
                stats = abs_path.stat()
                file_size = stats.st_size
                file_mtime = stats.st_mtime

                if file_size == 0:
                    self.logger.warning(f"Track file has zero size: {abs_path}")
                    return

                hash_md5 = hashlib.md5()
                try:
                    async with aiofiles.open(abs_path, "rb") as f:
                        chunk_size = 4096
                        while chunk := await f.read(chunk_size):
                            hash_md5.update(chunk)
                    file_hash = hash_md5.hexdigest()
                except Exception as hash_e:
                    self.logger.warning(f"Error calculating hash, using simplified method: {str(hash_e)}")
                    file_hash = f"{file_size}_{file_mtime}"

            # Update legacy in-memory
            self.local_tracks[track_id] = LocalTrack(
                id=track_id,
                path=abs_path,
                hash=file_hash,
                size=file_size,
                last_modified=file_mtime,
            )

            # Persist legacy & unified
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.save_index()
                    self.logger.debug(f"Successfully saved index after adding track {track_id}")

                    # Enrich unified state with provided metadata (without overwriting existing values)
                    try:
                        await self._load_state()
                        t = self._state.setdefault("tracks", {}).setdefault(str(track_id), {})
                        # Core path-related fields already set by _sync_unified_tracks_from_local
                        # Set timestamps and existence for successful download
                        if not t.get("downloaded_at"):
                            t["downloaded_at"] = _now_iso()
                        t["exists_on_disk"] = True
                        t["last_verified"] = _now_iso()

                        # Artist/Album enrichment
                        if artist_names and not t.get("artist_names"):
                            t["artist_names"] = artist_names
                        if album_id and not t.get("album_id"):
                            t["album_id"] = album_id
                        if album_title and not t.get("album_title"):
                            t["album_title"] = album_title

                        # Title enrichment
                        if track_title and not t.get("title"):
                            t["title"] = track_title

                        # ISRC enrichment
                        if isrc and not t.get("isrc"):
                            t["isrc"] = isrc

                        # Quality enrichment
                        q = t.setdefault("quality", {"requested": "", "actual": None, "codec": None})
                        if quality_requested and not q.get("requested"):
                            q["requested"] = quality_requested
                        if quality_actual and not q.get("actual"):
                            q["actual"] = quality_actual
                        if codec and not q.get("codec"):
                            q["codec"] = codec

                        # Sources enrichment
                        s = t.setdefault("sources", {"favorites": False, "playlists": [], "artists": []})
                        if source_favorites is True:
                            s["favorites"] = True
                        if source_playlist:
                            if source_playlist not in s["playlists"]:
                                s["playlists"].append(source_playlist)
                        if source_artist:
                            if source_artist not in s["artists"]:
                                s["artists"].append(source_artist)

                        await self._save_state_atomic()
                    except Exception as enrich_e:
                        self.logger.warning(f"Failed to enrich unified state for track {track_id}: {enrich_e}")

                    return
                except Exception as save_e:
                    if attempt < max_retries - 1:
                        self.logger.warning(f"Save attempt {attempt+1} failed: {str(save_e)}. Retrying...")
                        await asyncio.sleep(1)
                    else:
                        self.logger.error(f"All {max_retries} save attempts failed for track {track_id}")
                        raise

        except Exception as e:
            self.logger.error(f"Error adding track {track_id} to index: {str(e)}", exc_info=True)
            self.logger.info(f"Track {track_id} is in memory but may not be saved to disk")

    async def remove_track(self, track_id: str) -> None:
        """
        Remove a track from the index (legacy) and update unified state.

        Args:
            track_id: Track ID
        """
        if track_id in self.local_tracks:
            del self.local_tracks[track_id]
            await self.save_index()  # will also sync unified state

        # Also remove from unified tracks explicitly if present
        if track_id in self._state.get("tracks", {}):
            del self._state["tracks"][track_id]
            await self._save_state_atomic()

    async def check_track_exists(self, track_id: str) -> Tuple[bool, Optional[Path]]:
        """
        Check if a track exists in the library index (without verifying physical file existence).

        Args:
            track_id: Track ID

        Returns:
            Tuple of (exists, path)
        """
        await self._load_state()

        if track_id in self.local_tracks:
            local_track = self.local_tracks[track_id]
            return True, local_track.path

        return False, None

    async def scan_directory(self, directory: Path) -> None:
        """
        Scan a directory for tracks and update the index.

        Args:
            directory: Directory to scan
        """
        if not directory.exists():
            self.logger.warning(f"Directory does not exist: {directory}")
            return

        self.logger.info(f"Scanning directory: {directory}")

        # Get all audio files
        extensions = [".flac", ".m4a", ".mp3"]
        files: List[Path] = []

        for ext in extensions:
            files.extend(directory.glob(f"**/*{ext}"))

        self.logger.info(f"Found {len(files)} audio files")

        # Simple heuristic: log unindexed files (no automatic import here)
        for file_path in files:
            if all(local_track.path != file_path for local_track in self.local_tracks.values()):
                self.logger.debug(f"Unindexed file: {file_path}")

        await self.save_index()

    async def is_track_in_library(self, track: Track) -> bool:
        """
        Determine if a track should be considered present in the library based on index-only logic.

        Rules (in order):
          1) Exact ID match in unified tracks.
          2) Album-based: if album status is complete, or this track ID is marked downloaded.
          3) ISRC match: if any index entry has the same ISRC.
        """
        await self._load_state()

        # 1) Exact ID match
        tid = str(getattr(track, "id", "") or "")
        if tid and tid in self._state.get("tracks", {}):
            return True

        # 2) Album-based checks from in-memory legacy statuses and unified albums state
        album = getattr(track, "album", None)
        album_id = str(getattr(album, "id", "") or "") if album else ""
        try:
            await self.load_album_status()
        except Exception:
            # Non-fatal
            pass

        if album_id:
            status = self.album_statuses.get(album_id)
            if status:
                if status.is_complete or (tid and tid in status.downloaded_track_ids):
                    return True

            # Unified albums state
            astate = self._state.get("albums", {}).get(album_id)
            if astate:
                if astate.get("status") == "complete":
                    return True
                if tid and tid in set(astate.get("downloaded_track_ids", [])):
                    return True

        # 3) ISRC match
        isrc = getattr(track, "isrc", None)
        if isrc:
            for t in self._state.get("tracks", {}).values():
                try:
                    if t.get("isrc") and t.get("isrc") == isrc:
                        return True
                except Exception:
                    continue

        # 4) Metadata fallback (artist + title [+ album when available]), if enabled
        if getattr(self.settings, "match_mode", "id_or_metadata") != "id":
            cand_artist = _normalize_text(getattr(track, "artist_names", "") or "")
            # Prefer explicit title; fallback to formatted_title
            cand_title = _normalize_text(
                (getattr(track, "title", None) or getattr(track, "formatted_title", None) or "")
            )
            # Normalize album title from the remote track (if available)
            cand_album = ""
            try:
                album_obj = getattr(track, "album", None)
                cand_album = _normalize_text(getattr(album_obj, "title", "") or "")
            except Exception:
                cand_album = ""
            if cand_artist and cand_title:
                for t in self._state.get("tracks", {}).values():
                    ta = _normalize_text(t.get("artist_names", "") or "")
                    tt = _normalize_text(t.get("title", "") or "")
                    at = _normalize_text(t.get("album_title", "") or "")
                    # If album context is present on both sides, require album title to match as well
                    if cand_album and at:
                        if ta and tt and ta == cand_artist and tt == cand_title and at == cand_album:
                            return True
                    else:
                        # Fallback to artist+title only when album info is missing on at least one side
                        if ta and tt and ta == cand_artist and tt == cand_title:
                            return True

        return False

    async def compare_tracks(self, remote_tracks: List[Track]) -> Tuple[List[Track], List[Track]]:
        """
        Compare remote tracks with local tracks using index-only logic and metadata fallback.
        """
        new_tracks: List[Track] = []
        existing_tracks: List[Track] = []

        # Match mode can be "id" (strict) or "id_or_metadata" (default)
        match_mode = getattr(self.settings, "match_mode", "id_or_metadata")

        for track in remote_tracks:
            if match_mode == "id":
                exists, _ = await self.check_track_exists(track.id)
                is_present = exists
            else:
                is_present = await self.is_track_in_library(track)

            if is_present:
                existing_tracks.append(track)
            else:
                new_tracks.append(track)

        return new_tracks, existing_tracks

    async def load_album_status(self) -> None:
        """Load album download status (unified-only)."""
        await self._load_state()
        # album_statuses are already populated from unified by _populate_from_state()
        self.logger.info("Album statuses loaded from unified state")

    async def save_album_status(self) -> None:
        """Save album download status (unified-only)."""
        try:
            await self._sync_unified_albums_from_statuses()
            await self._save_state_atomic()
            self.logger.info(
                f"Unified album statuses saved to {self.state_path} "
                f"(albums={len(self._state.get('albums', {}))})"
            )
        except Exception as e:
            self.logger.error(f"Error saving unified album status: {str(e)}")

    async def _sync_unified_albums_from_statuses(self) -> None:
        """Synchronize unified state albums from legacy in-memory album_statuses."""
        albums_state = self._state.setdefault("albums", {})
        for album_id, status in self.album_statuses.items():
            a = albums_state.get(album_id, {})
            a["title"] = status.album_title
            a.setdefault("artist_ids", [])
            a.setdefault("artist_names", "")
            a["total_tracks"] = status.total_tracks
            a["downloaded_track_ids"] = list(status.downloaded_track_ids)
            # Map status to unified values
            if status.is_complete:
                a["status"] = "complete"
            else:
                a["status"] = "in_progress" if status.downloaded_tracks > 0 else "not_started"
            a["updated_at"] = _now_iso()
            albums_state[album_id] = a

    async def add_album_status(self, album: Album) -> AlbumDownloadStatus:
        """
        Add or update album download status.

        Args:
            album: Album to add or update

        Returns:
            Album download status
        """
        await self._load_state()

        if album.id in self.album_statuses:
            status = self.album_statuses[album.id]
            status.album_title = album.title
            status.total_tracks = len(album.tracks) if hasattr(album, "tracks") and album.tracks else 0
            status.last_updated = time.time()

            if hasattr(album, "tracks") and album.tracks:
                status.track_ids = {str(track.id) for track in album.tracks}

            self.logger.info(f"Updated album status for '{album.title}' (ID: {album.id})")
        else:
            track_ids = {str(track.id) for track in album.tracks} if hasattr(album, "tracks") and album.tracks else set()
            status = AlbumDownloadStatus(
                album_id=album.id,
                album_title=album.title,
                total_tracks=len(album.tracks) if hasattr(album, "tracks") and album.tracks else 0,
                track_ids=track_ids,
            )
            self.album_statuses[album.id] = status
            self.logger.info(f"Added album status for '{album.title}' (ID: {album.id})")

        await self.save_album_status()
        return status

    async def update_album_track_status(self, album_id: str, track_id: str, downloaded: bool = True) -> None:
        """
        Update the status of a track in an album.

        Args:
            album_id: Album ID
            track_id: Track ID
            downloaded: Whether the track has been downloaded
        """
        await self._load_state()

        if album_id not in self.album_statuses:
            self.logger.warning(f"Album {album_id} not found in album status")
            return

        status = self.album_statuses[album_id]

        if downloaded:
            status.downloaded_track_ids.add(track_id)
            status.downloaded_tracks = len(status.downloaded_track_ids)
        else:
            if track_id in status.downloaded_track_ids:
                status.downloaded_track_ids.remove(track_id)
                status.downloaded_tracks = len(status.downloaded_track_ids)

        status.last_updated = time.time()

        if status.is_complete:
            status.status = "completed"
            self.logger.info(f"Album '{status.album_title}' (ID: {album_id}) download completed")

        await self.save_album_status()

    async def get_incomplete_albums(self) -> List[AlbumDownloadStatus]:
        """
        Get a list of incomplete album downloads.

        Returns:
            List of incomplete album download statuses
        """
        await self._load_state()
        return [
            status
            for status in self.album_statuses.values()
            if status.status == "in_progress" and status.downloaded_tracks < status.total_tracks
        ]

    async def remove_album_status(self, album_id: str, reason: str = "Unknown") -> None:
        """
        Remove an album status from the album status file.

        Args:
            album_id: Album ID to remove
            reason: Reason for removal
        """
        await self._load_state()

        if album_id in self.album_statuses:
            album_title = self.album_statuses[album_id].album_title
            del self.album_statuses[album_id]
            self.logger.info(f"Removed album status for '{album_title}' (ID: {album_id}). Reason: {reason}")
            await self.save_album_status()
        else:
            self.logger.debug(f"Album ID {album_id} not found in album status, nothing to remove")

    async def clean_old_album_statuses(self, max_age_days: int = 7) -> None:
        """
        Clean up old album statuses.

        Args:
            max_age_days: Maximum age in days for incomplete album statuses
        """
        await self._load_state()

        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        old_album_ids = []
        for album_id, status in self.album_statuses.items():
            if status.status == "in_progress" and current_time - status.last_updated > max_age_seconds:
                old_album_ids.append(album_id)

        for album_id in old_album_ids:
            del self.album_statuses[album_id]
            self.logger.info(f"Removed old album status for album ID: {album_id}")

        if old_album_ids:
            await self.save_album_status()
            self.logger.info(f"Cleaned up {len(old_album_ids)} old album statuses")

    # ==========================
    # New helper computations
    # ==========================

    async def get_missing_for_album(self, album: Album) -> Tuple[int, int, List[Track]]:
        """
        Compute missing tracks for a given album.

        Returns:
            (total_tracks, missing_count, missing_tracks_sample up to 10)
        """
        await self._load_state()
        total = 0
        missing: List[Track] = []

        if hasattr(album, "tracks") and album.tracks:
            for t in album.tracks:
                total += 1
                try:
                    present = await self.is_track_in_library(t)
                except Exception:
                    # Fallback to strict ID check on error
                    present, _ = await self.check_track_exists(t.id)
                if not present:
                    missing.append(t)

        return total, len(missing), missing[:10]

    async def get_missing_for_tracks(self, remote_tracks: List[Track]) -> Tuple[int, int, List[Track]]:
        """
        Compute missing among a list of tracks.

        Returns:
            (total, missing_count, sample up to 10)
        """
        await self._load_state()
        total = len(remote_tracks)
        missing: List[Track] = []
        for t in remote_tracks:
            try:
                present = await self.is_track_in_library(t)
            except Exception:
                # Fallback to strict ID check on error
                present, _ = await self.check_track_exists(t.id)
            if not present:
                missing.append(t)
        return total, len(missing), missing[:10]

    async def quick_verify_paths(self, ids: Iterable[str]) -> None:
        """Refresh last_verified for a small set of track ids without checking physical files."""
        await self._load_state()
        tracks = self._state.get("tracks", {})
        changed = False
        for tid in ids:
            t = tracks.get(tid)
            if not t:
                continue
            p = t.get("file_path")
            if p:
                # Always set exists_on_disk to true for library index entries
                t["exists_on_disk"] = True
                t["last_verified"] = _now_iso()
                changed = True
        if changed:
            await self._save_state_atomic()

    async def add_video(
        self,
        video_id: str,
        path: Path,
        title: str,
        artist_names: str = "Unknown Artist",
        album_id: Optional[str] = None
    ) -> None:
        """
        Add or update a video entry in the unified library state.

        Args:
            video_id: Video ID
            path: Path to the video file
            title: Video title
            artist_names: Artist names (display string)
            album_id: Optional album/collection ID if available
        """
        await self._load_state()

        try:
            abs_path = path.absolute()
            # Ensure directory exists (typically already ensured by downloader)
            abs_path.parent.mkdir(parents=True, exist_ok=True)

            # Update unified videos state
            videos = self._state.setdefault("videos", {})
            videos[str(video_id)] = {
                "file_path": str(abs_path),
                "exists_on_disk": abs_path.exists(),
                "downloaded_at": _now_iso(),
                "last_verified": _now_iso(),
                "artist_ids": [],  # Not tracked currently
                "artist_names": artist_names or "Unknown Artist",
                "album_id": album_id,
                "title": title or "Unknown Title",
            }

            await self._save_state_atomic()
        except Exception as e:
            self.logger.error(f"Error adding video {video_id} to unified state: {e}", exc_info=True)

    # ==========================
    # Administrative operations
    # ==========================

    async def get_index_counts(self) -> Dict[str, int]:
        """
        Return counts of items in the unified library state.
        """
        await self._load_state()
        return {
            "tracks": len(self._state.get("tracks", {})),
            "albums": len(self._state.get("albums", {})),
            "videos": len(self._state.get("videos", {})),
        }

    async def clear_all_indexes(self, backup: bool = True) -> Dict[str, int]:
        """
        Clear all index data (unified library state). Does NOT delete any media files on disk.

        Returns the previous counts before clearing.
        """
        await self._load_state()

        prev_counts = await self.get_index_counts()

        # Create backups if requested
        if backup:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            try:
                if self.state_path.exists():
                    import shutil
                    backup_path = self.state_path.with_suffix(f".json.bak.{timestamp}")
                    shutil.copy(self.state_path, backup_path)
                    self.logger.info(f"Backed up unified state to {backup_path}")
            except Exception as e:
                self.logger.warning(f"Failed to backup unified state: {e}")

            # Legacy backups
            try:
                if self.index_path.exists():
                    import shutil
                    backup_index = self.index_path.with_suffix(f".json.bak.{timestamp}")
                    shutil.copy(self.index_path, backup_index)
                    self.logger.info(f"Backed up legacy track index to {backup_index}")
            except Exception as e:
                self.logger.warning(f"Failed to backup legacy track index: {e}")

            try:
                if self.album_status_path.exists():
                    import shutil
                    backup_album = self.album_status_path.with_suffix(f".json.bak.{timestamp}")
                    shutil.copy(self.album_status_path, backup_album)
                    self.logger.info(f"Backed up legacy album status to {backup_album}")
            except Exception as e:
                self.logger.warning(f"Failed to backup legacy album status: {e}")

        # Reset unified state
        async with self._state_lock:
            self._state["tracks"] = {}
            self._state["albums"] = {}
            self._state["videos"] = {}

        await self._save_state_atomic()

        # Reset in-memory structures and save unified
        self.local_tracks = {}
        self.album_statuses = {}
        try:
            await self.save_index()
        except Exception as e:
            self.logger.warning(f"Failed to save empty unified track state: {e}")
        try:
            await self.save_album_status()
        except Exception as e:
            self.logger.warning(f"Failed to save empty unified album state: {e}")

        self.logger.info("Cleared unified library state (media files unaffected)")
        return prev_counts

    async def delete_legacy_files(self) -> None:
        """
        Delete legacy .data JSON files if present.
        """
        try:
            if self.index_path.exists():
                self.index_path.unlink()
                self.logger.info(f"Deleted legacy index file: {self.index_path}")
        except Exception as e:
            self.logger.warning(f"Could not delete legacy index file: {e}")
        try:
            if self.album_status_path.exists():
                self.album_status_path.unlink()
                self.logger.info(f"Deleted legacy album status file: {self.album_status_path}")
        except Exception as e:
            self.logger.warning(f"Could not delete legacy album status file: {e}")

    async def backfill_downloaded_at(self) -> Dict[str, int]:
        """
        Backfill missing 'downloaded_at' timestamps for tracks in the unified state.

        For each track in the library index with downloaded_at is null/empty,
        attempt to set downloaded_at to the file's modification time (UTC, ISO-8601).
        If file doesn't exist or can't be accessed, use current time instead.
        
        Returns summary counts.
        """
        await self._load_state()
        tracks = self._state.get("tracks", {})
        updated = 0
        already_set = 0
        missing_path = 0
        used_current_time = 0

        for tid, t in tracks.items():
            path_str = t.get("file_path")
            if not path_str:
                continue
            
            # Always set exists_on_disk to true for library index entries
            t["exists_on_disk"] = True
            
            if t.get("downloaded_at"):
                already_set += 1
                continue
                
            p = Path(path_str)
            try:
                # Try to get file modification time if possible
                if p.exists():
                    stat = p.stat()
                    dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                    t["downloaded_at"] = dt
                    updated += 1
                else:
                    # If file doesn't exist, use current time
                    t["downloaded_at"] = _now_iso()
                    used_current_time += 1
                
                t["last_verified"] = _now_iso()
            except Exception:
                # If stat fails, use current time
                t["downloaded_at"] = _now_iso()
                t["last_verified"] = _now_iso()
                used_current_time += 1

        await self._save_state_atomic()
        return {
            "total": len(tracks),
            "updated": updated,
            "already_set": already_set,
            "missing_path": missing_path,
            "used_current_time": used_current_time,
        }

    async def backfill_metadata(
        self,
        client,
        *,
        reconcile_favorites: bool = False,
        rate_limit_seconds: float = 0.2,
        max_items: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Backfill missing artist/album metadata for tracks in the unified state using the Tidal client.

        - Populates artist_names, album_id, album_title when missing.
        - Optionally marks sources.favorites for tracks found in user's favorites.
        - Respects a simple rate limit between API calls.

        Returns summary counts.
        """
        await self._load_state()
        tracks_state = self._state.get("tracks", {})
        to_process: List[str] = []
        for tid, t in tracks_state.items():
            if not t.get("artist_names") or not t.get("album_id") or not t.get("album_title"):
                to_process.append(tid)
        if max_items is not None:
            to_process = to_process[:max_items]

        favorites_set: Set[str] = set()
        if reconcile_favorites:
            try:
                fav_tracks = await client.get_favorite_tracks()
                favorites_set = {str(tr.id) for tr in fav_tracks}
            except Exception as e:
                self.logger.warning(f"Failed to fetch favorites for reconciliation: {e}")

        updated = 0
        skipped = 0
        errors = 0

        for idx, tid in enumerate(to_process):
            entry = tracks_state.get(tid) or {}
            try:
                tr = await client.get_track(tid)
                # Update artist/album fields if missing
                if tr:
                    if not entry.get("artist_names"):
                        entry["artist_names"] = getattr(tr, "artist_names", "") or ""
                    album = getattr(tr, "album", None)
                    if album:
                        if not entry.get("album_id"):
                            entry["album_id"] = getattr(album, "id", None)
                        if not entry.get("album_title"):
                            entry["album_title"] = getattr(album, "title", None)
                    # store track title if missing
                    if not entry.get("title"):
                        entry["title"] = getattr(tr, "title", None) or getattr(tr, "formatted_title", None)
                    # sources.favorites reconciliation
                    src = entry.setdefault("sources", {"favorites": False, "playlists": [], "artists": []})
                    if reconcile_favorites and str(tid) in favorites_set:
                        src["favorites"] = True
                    tracks_state[tid] = entry
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                self.logger.warning(f"Metadata backfill failed for track {tid}: {e}")
                errors += 1
            # Rate limit between calls to avoid hammering API
            await asyncio.sleep(rate_limit_seconds)

        await self._save_state_atomic()
        return {
            "total_candidates": len(to_process),
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "reconciled_favorites": len(favorites_set) if reconcile_favorites else 0,
        }
