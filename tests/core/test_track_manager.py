import asyncio
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio # Explicit import for clarity, though often not needed for usage
import aiofiles

from riptidal.core.track_manager import TrackManager, LocalTrack
from riptidal.core.settings import Settings
from riptidal.api.models import Track as ApiTrack, Album as ApiAlbum # Alias to avoid confusion
from riptidal.core.download_models import AlbumDownloadStatus


@pytest.fixture
def mock_settings(tmp_path):
    """Provides a mock Settings object with a temporary download path."""
    settings = MagicMock(spec=Settings)
    settings.download_path = tmp_path / "downloads"
    settings.download_path.mkdir(parents=True, exist_ok=True)
    return settings

@pytest_asyncio.fixture
async def track_manager(mock_settings, tmp_path):
    """
    Provides a TrackManager instance with get_data_dir patched
    to use a temporary directory.
    """
    data_dir = tmp_path / ".data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('riptidal.core.track_manager.get_data_dir', return_value=data_dir):
        with patch('riptidal.core.track_manager.TrackManager._check_old_index', return_value=asyncio.Future()) as mock_check_old:
            mock_check_old.return_value.set_result(False)
            tm = TrackManager(settings=mock_settings)
            yield tm

@pytest.mark.asyncio
async def test_track_manager_initialization(track_manager, tmp_path):
    """Test that TrackManager initializes paths correctly."""
    expected_data_dir = tmp_path / ".data"
    assert track_manager.index_path == expected_data_dir / "track_index.json"
    assert track_manager.album_status_path == expected_data_dir / "album_status.json"
    assert isinstance(track_manager.local_tracks, dict)
    assert isinstance(track_manager.album_statuses, dict)

@pytest.mark.asyncio
async def test_load_index_no_file_creates_empty_index(track_manager):
    """Test load_index creates an empty index file if none exists."""
    assert not track_manager.index_path.exists()
    
    await track_manager.load_index()
    
    assert track_manager.index_path.exists()
    assert len(track_manager.local_tracks) == 0
    async with aiofiles.open(track_manager.index_path, "r") as f:
        content = await f.read()
        assert json.loads(content) == {}

@pytest.mark.asyncio
async def test_load_index_empty_file(track_manager):
    """Test load_index with an existing empty JSON file."""
    # Create an empty JSON file
    async with aiofiles.open(track_manager.index_path, "w") as f:
        await f.write("{}")
    
    await track_manager.load_index()
    
    assert len(track_manager.local_tracks) == 0

@pytest.mark.asyncio
async def test_load_index_empty_string_file(track_manager):
    """Test load_index with an existing file that is completely empty (not even {})."""
    async with aiofiles.open(track_manager.index_path, "w") as f:
        await f.write("")
    
    await track_manager.load_index()
    
    assert len(track_manager.local_tracks) == 0

@pytest.mark.asyncio
async def test_save_index_empty(track_manager):
    """Test saving an empty index."""
    track_manager.local_tracks = {} # Ensure it's empty
    await track_manager.save_index()
    
    assert track_manager.index_path.exists()
    async with aiofiles.open(track_manager.index_path, "r") as f:
        content = await f.read()
        assert json.loads(content) == {}

@pytest.mark.asyncio
async def test_add_track_and_save(track_manager, mock_settings, tmp_path):
    """Test adding a track and that it gets saved to the index."""
    # Create a dummy track file
    dummy_file_path = mock_settings.download_path / "artist" / "album" / "track1.flac"
    dummy_file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dummy_file_path, "w") as f:
        await f.write("dummy audio data")

    track_id = "test_track_123"
    await track_manager.add_track(track_id, dummy_file_path)

    assert track_id in track_manager.local_tracks
    local_track_entry = track_manager.local_tracks[track_id]
    assert local_track_entry.id == track_id
    assert local_track_entry.path == dummy_file_path.absolute()
    assert local_track_entry.size == len("dummy audio data")
    assert local_track_entry.hash is not None 

    async with aiofiles.open(track_manager.index_path, "r") as f:
        content = await f.read()
        saved_index_data = json.loads(content)
    
    assert track_id in saved_index_data
    assert saved_index_data[track_id]["path"] == str(dummy_file_path.absolute())
    assert saved_index_data[track_id]["size"] == len("dummy audio data")

@pytest.mark.asyncio
async def test_load_index_with_data(track_manager, mock_settings, tmp_path):
    """Test loading an index file that has data."""
    # Create a dummy track file and add it to simulate a saved index
    dummy_file_path = mock_settings.download_path / "track2.flac"
    dummy_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure parent exists
    async with aiofiles.open(dummy_file_path, "w") as f:
        await f.write("more audio")
    
    track_id = "track_456"
    stats = dummy_file_path.stat()
    index_content = {
        track_id: {
            "path": str(dummy_file_path.absolute()),
            "hash": "manual_hash_example",
            "size": stats.st_size,
            "last_modified": stats.st_mtime
        }
    }
    async with aiofiles.open(track_manager.index_path, "w") as f:
        await f.write(json.dumps(index_content, indent=2))

    await track_manager.load_index()

    assert track_id in track_manager.local_tracks
    loaded_track = track_manager.local_tracks[track_id]
    assert loaded_track.path == dummy_file_path.absolute()
    assert loaded_track.hash == "manual_hash_example"
    assert loaded_track.size == stats.st_size


@pytest.mark.asyncio
async def test_remove_track(track_manager, mock_settings, tmp_path):
    """Test removing a track from the index."""
    # Add a track first
    dummy_file_path = mock_settings.download_path / "track_to_remove.flac"
    dummy_file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dummy_file_path, "w") as f:
        await f.write("some data")
    
    track_id = "track_to_remove_123"
    await track_manager.add_track(track_id, dummy_file_path)
    assert track_id in track_manager.local_tracks

    # Remove the track
    await track_manager.remove_track(track_id)
    assert track_id not in track_manager.local_tracks

    # Verify it's removed from the saved index file
    async with aiofiles.open(track_manager.index_path, "r") as f:
        content = await f.read()
        saved_index_data = json.loads(content)
    assert track_id not in saved_index_data

@pytest.mark.asyncio
async def test_remove_nonexistent_track(track_manager):
    """Test attempting to remove a track ID that is not in the index."""
    initial_local_tracks_copy = track_manager.local_tracks.copy()
    initial_index_content = {}
    if track_manager.index_path.exists():
        async with aiofiles.open(track_manager.index_path, "r") as f:
            initial_index_content = json.loads(await f.read())

    await track_manager.remove_track("nonexistent_track_id_404")

    assert track_manager.local_tracks == initial_local_tracks_copy
    if track_manager.index_path.exists():
        async with aiofiles.open(track_manager.index_path, "r") as f:
            current_index_content = json.loads(await f.read())
        if not initial_local_tracks_copy:
             assert current_index_content == {}
        else:
            assert current_index_content == initial_index_content


@pytest.mark.asyncio
async def test_check_track_exists_in_index_and_file_exists(track_manager, mock_settings, tmp_path):
    """Track is in index, and its file exists on disk."""
    dummy_file_path = mock_settings.download_path / "existing_track.mp3"
    dummy_file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dummy_file_path, "w") as f:
        await f.write("audio content")
    
    track_id = "existing_track_001"
    await track_manager.add_track(track_id, dummy_file_path) # Adds to index and saves

    exists, path = await track_manager.check_track_exists(track_id)
    assert exists is True
    assert path == dummy_file_path.absolute()

@pytest.mark.asyncio
async def test_check_track_exists_in_index_but_file_missing(track_manager, mock_settings, tmp_path):
    """Track is in index, but its file has been removed from disk."""
    dummy_file_path = mock_settings.download_path / "ghost_track.m4a"
    dummy_file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dummy_file_path, "w") as f: # Create the file initially
        await f.write("temporary content")

    track_id = "ghost_track_002"
    await track_manager.add_track(track_id, dummy_file_path) # Add to index
    assert track_id in track_manager.local_tracks

    dummy_file_path.unlink() # Delete the file from disk
    assert not dummy_file_path.exists()

    exists, path = await track_manager.check_track_exists(track_id)
    assert exists is False
    assert path is None
    assert track_id not in track_manager.local_tracks # Should be removed from in-memory index

    # Verify it's also removed from the saved index file
    async with aiofiles.open(track_manager.index_path, "r") as f:
        content = await f.read()
        saved_index_data = json.loads(content)
    assert track_id not in saved_index_data


@pytest.mark.asyncio
async def test_check_track_exists_not_in_index(track_manager):
    """Track is not in the index."""
    exists, path = await track_manager.check_track_exists("track_not_in_index_777")
    assert exists is False
    assert path is None


# Tests for Album Status Management
@pytest.mark.asyncio
async def test_load_album_status_no_file(track_manager):
    """Test load_album_status when the status file doesn't exist."""
    assert not track_manager.album_status_path.exists()
    await track_manager.load_album_status()
    assert len(track_manager.album_statuses) == 0
    # Unlike index, album_status file is not created by load if not exists.

@pytest.mark.asyncio
async def test_save_album_status_empty(track_manager):
    """Test saving empty album statuses."""
    track_manager.album_statuses = {}
    await track_manager.save_album_status()
    
    assert track_manager.album_status_path.exists()
    async with aiofiles.open(track_manager.album_status_path, "r") as f:
        content = await f.read()
        assert json.loads(content) == {}

@pytest.mark.asyncio
async def test_add_album_status_new_and_load(track_manager):
    """Test adding a new album status and then loading it."""
    # Mock an ApiAlbum and its tracks
    mock_track1 = MagicMock(spec=ApiTrack)
    mock_track1.id = "t1"
    mock_track2 = MagicMock(spec=ApiTrack)
    mock_track2.id = "t2"
    
    mock_album = MagicMock(spec=ApiAlbum)
    mock_album.id = "album123"
    mock_album.title = "Test Album Title"
    mock_album.tracks = [mock_track1, mock_track2]

    await track_manager.add_album_status(mock_album)

    assert "album123" in track_manager.album_statuses
    status = track_manager.album_statuses["album123"]
    assert status.album_id == "album123"
    assert status.album_title == "Test Album Title"
    assert status.total_tracks == 2
    assert status.track_ids == {"t1", "t2"}
    assert status.downloaded_tracks == 0
    assert status.status == "in_progress"

    async with aiofiles.open(track_manager.album_status_path, "r") as f:
        content = await f.read()
        saved_data = json.loads(content)
    
    assert "album123" in saved_data
    assert saved_data["album123"]["album_title"] == "Test Album Title"
    assert saved_data["album123"]["total_tracks"] == 2
    assert set(saved_data["album123"]["track_ids"]) == {"t1", "t2"}

    new_tm = TrackManager(settings=track_manager.settings)
    await new_tm.load_album_status()
    assert "album123" in new_tm.album_statuses
    loaded_status = new_tm.album_statuses["album123"]
    assert loaded_status.album_title == "Test Album Title"
    assert loaded_status.track_ids == {"t1", "t2"}


@pytest.mark.asyncio
async def test_update_album_track_status_downloaded(track_manager):
    """Test updating a track in an album as downloaded."""
    mock_track1 = MagicMock(spec=ApiTrack); mock_track1.id = "trackA"
    mock_track2 = MagicMock(spec=ApiTrack); mock_track2.id = "trackB"
    mock_album = MagicMock(spec=ApiAlbum)
    mock_album.id = "album789"; mock_album.title = "Update Test Album"; mock_album.tracks = [mock_track1, mock_track2]
    await track_manager.add_album_status(mock_album)

    await track_manager.update_album_track_status("album789", "trackA", downloaded=True)
    
    status = track_manager.album_statuses["album789"]
    assert "trackA" in status.downloaded_track_ids
    assert status.downloaded_tracks == 1
    assert status.status == "in_progress"

    await track_manager.update_album_track_status("album789", "trackB", downloaded=True)
    status = track_manager.album_statuses["album789"]
    assert "trackB" in status.downloaded_track_ids
    assert status.downloaded_tracks == 2
    assert status.is_complete is True
    assert status.status == "completed"

@pytest.mark.asyncio
async def test_get_incomplete_albums(track_manager):
    """Test retrieving incomplete albums."""
    # Album 1: Incomplete
    mock_t1 = MagicMock(spec=ApiTrack); mock_t1.id = "t1_a1"
    mock_t2 = MagicMock(spec=ApiTrack); mock_t2.id = "t2_a1"
    mock_a1 = MagicMock(spec=ApiAlbum); mock_a1.id = "a1"; mock_a1.title = "Album One"; mock_a1.tracks = [mock_t1, mock_t2]
    await track_manager.add_album_status(mock_a1)
    await track_manager.update_album_track_status("a1", "t1_a1", downloaded=True)

    mock_t3 = MagicMock(spec=ApiTrack); mock_t3.id = "t3_a2"
    mock_a2 = MagicMock(spec=ApiAlbum); mock_a2.id = "a2"; mock_a2.title = "Album Two"; mock_a2.tracks = [mock_t3]
    await track_manager.add_album_status(mock_a2)
    await track_manager.update_album_track_status("a2", "t3_a2", downloaded=True)
    
    mock_t4 = MagicMock(spec=ApiTrack); mock_t4.id = "t4_a4"
    mock_a4 = MagicMock(spec=ApiAlbum); mock_a4.id = "a4"; mock_a4.title = "Album Four"; mock_a4.tracks = [mock_t4]
    await track_manager.add_album_status(mock_a4)


    incomplete_albums = await track_manager.get_incomplete_albums()
    assert len(incomplete_albums) == 2
    incomplete_album_ids = {s.album_id for s in incomplete_albums}
    assert "a1" in incomplete_album_ids
    assert "a4" in incomplete_album_ids
    assert "a2" not in incomplete_album_ids
