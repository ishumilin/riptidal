import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from riptidal.core.downloader import TrackDownloader
from riptidal.api.models import Track as ApiTrack, Album as ApiAlbum, Artist as ApiArtist
from riptidal.core.settings import Settings

@pytest.fixture
def mock_client():
    return MagicMock()

@pytest.fixture
def mock_track_manager():
    return MagicMock()

@pytest.fixture
def base_settings(tmp_path):
    download_dir = tmp_path / "test_downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    return Settings(
        download_path=download_dir,
        track_path_format="{artist_name}/{album_name}/{track_number} - {track_title}",
    )

@pytest.fixture
def track_downloader(mock_client, base_settings, mock_track_manager):
    return TrackDownloader(
        client=mock_client,
        settings=base_settings,
        track_manager=mock_track_manager
    )

# Helper to create mock Artist objects
def create_artist(id_val, name_val):
    artist = MagicMock(spec=ApiArtist)
    artist.id = str(id_val)
    artist.name = name_val
    return artist

# Helper to create mock Album objects
def create_album(id_val, title_val, artists_list, release_date_val=None):
    album = MagicMock(spec=ApiAlbum)
    album.id = str(id_val)
    album.title = title_val
    album.artists = artists_list
    album.releaseDate = release_date_val
    album.release_year = int(release_date_val.split("-")[0]) if release_date_val else None
    return album

# Helper to create mock Track objects
def create_track(id_val, title_val, artists_list, album_obj=None, track_num=1, explicit_val=False, version_val=None):
    track = MagicMock(spec=ApiTrack)
    track.id = str(id_val)
    track.title = title_val
    track.artists = artists_list
    track.artist_names = ", ".join(a.name for a in artists_list) # Simulate property
    track.album = album_obj
    track.trackNumber = track_num
    track.explicit = explicit_val
    track.version = version_val
    track.formatted_title = f"{title_val} ({version_val})" if version_val else title_val
    return track

def test_get_track_path_basic(track_downloader, base_settings):
    artist1 = create_artist("a1", "Artist Name")
    album1 = create_album("alb1", "Album Title", [artist1], "2023-01-01")
    track1 = create_track("t1", "Track Title", [artist1], album1, 1)

    path = track_downloader._get_track_path(track1, album1)
    expected = base_settings.download_path / "Artist Name" / "Album Title" / "01 - Track Title.flac"
    assert path == expected

def test_get_track_path_album_artist_priority(track_downloader, base_settings):
    album_artist = create_artist("aa1", "Album Main Artist")
    track_artist = create_artist("ta1", "Track Specific Artist")
    album1 = create_album("alb2", "Album Prio", [album_artist], "2023-02-01")
    track1 = create_track("t2", "Track Prio", [track_artist], album1, 2) 

    path = track_downloader._get_track_path(track1, album1)
    expected = base_settings.download_path / "Album Main Artist" / "Album Prio" / "02 - Track Prio.flac"
    assert path == expected

def test_get_track_path_track_album_artist_if_album_param_missing_artists(track_downloader, base_settings):
    track_artist_on_album_obj = create_artist("taa1", "Artist On TrackAlbumObj")
    
    album_on_track = create_album("alb_on_track", "Track's Album", [track_artist_on_album_obj])
    
    param_album = MagicMock(spec=ApiAlbum)
    param_album.id = "alb_param"
    param_album.title = "Param Album Title"
    param_album.artists = []
    param_album.releaseDate = None
    param_album.release_year = None

    track1 = create_track("t3", "Track Fallback", [create_artist("tr_art", "Track Artist")], album_on_track, 3)

    path = track_downloader._get_track_path(track1, param_album)
    expected = base_settings.download_path / "Artist On TrackAlbumObj" / "Param Album Title" / "03 - Track Fallback.flac"
    assert path == expected


def test_get_track_path_no_album_context(track_downloader, base_settings):
    track_artist = create_artist("noalb_a", "Artist NoAlbum")
    track1 = create_track("t4", "Track NoAlbumCtx", [track_artist], None, 4)

    path = track_downloader._get_track_path(track1, None)
    expected = base_settings.download_path / "Artist NoAlbum" / "Unknown Album" / "04 - Track NoAlbumCtx.flac"
    assert path == expected

def test_get_track_path_with_version_and_explicit(track_downloader, base_settings):
    artist1 = create_artist("a5", "Artist Explicit")
    album1 = create_album("alb5", "Album Explicit", [artist1], "2023-05-05")
    track1 = create_track("t5", "Track Explicit", [artist1], album1, 5, explicit_val=True, version_val="Radio Edit")

    # Update settings for this test to include explicit tag in format
    base_settings.track_path_format = "{artist_name}/{album_name}/{track_number} - {track_title} {explicit}"
    
    path = track_downloader._get_track_path(track1, album1)
    expected_title_part = "05 - Track Explicit (Radio Edit) [E]"
    expected = base_settings.download_path / "Artist Explicit" / "Album Explicit" / (expected_title_part + ".flac")
    assert path == expected

def test_get_track_path_custom_format(track_downloader, base_settings):
    artist1 = create_artist("a6", "Artist Custom")
    album1 = create_album("alb6", "Album Custom", [artist1], "2023-06-06")
    track1 = create_track("t6", "Track Custom", [artist1], album1, 1)

    base_settings.track_path_format = "{album_year}/{artist_name}/{album_name}/{track_title}"
    
    path = track_downloader._get_track_path(track1, album1)
    
    expected = base_settings.download_path / "2023" / "Artist Custom" / "Album Custom" / "Track Custom.flac"
    assert path == expected


def test_get_track_path_album_artist_caching(track_downloader, base_settings):
    album_artist = create_artist("aa_cache", "Cached Album Artist")
    track1_artist = create_artist("t1a_cache", "Track1 Artist")
    track2_artist = create_artist("t2a_cache", "Track2 Artist")
    
    album = create_album("alb_cache", "Caching Test Album", [album_artist])
    
    track1 = create_track("tr1_cache", "First Track", [track1_artist], album, track_num=1)
    track2 = create_track("tr2_cache", "Second Track", [track2_artist], album, track_num=2)

    path1 = track_downloader._get_track_path(track1, album)
    expected1 = base_settings.download_path / "Cached Album Artist" / "Caching Test Album" / "01 - First Track.flac"
    assert path1 == expected1
    assert album.id in track_downloader._album_artist_cache
    assert track_downloader._album_artist_cache[album.id] == "Cached Album Artist"

    path2 = track_downloader._get_track_path(track2, album)
    expected2 = base_settings.download_path / "Cached Album Artist" / "Caching Test Album" / "02 - Second Track.flac"
    assert path2 == expected2


# Tests for TrackDownloader.download_track method
@pytest.mark.asyncio
async def test_download_track_success(track_downloader, base_settings, mock_track_manager):
    mock_artist = create_artist("art_dl", "DL Artist")
    mock_album_obj = create_album("alb_dl", "DL Album", [mock_artist])
    mock_track_obj = create_track("trk_dl", "DL Track", [mock_artist], mock_album_obj)
    
    expected_path = base_settings.download_path / "DL Artist" / "DL Album" / "01 - DL Track.flac"

    track_downloader._get_track_path = MagicMock(return_value=expected_path)
    track_downloader._check_file_exists = AsyncMock(return_value=(False, None))
    track_downloader._check_track_availability = AsyncMock(return_value=(True, None))
    
    mock_stream_url = MagicMock()
    mock_stream_url.url = "http://example.com/stream"
    mock_stream_url.soundQuality = "LOSSLESS"
    track_downloader.client.get_stream_url = AsyncMock(return_value=mock_stream_url)
    
    track_downloader._download_file = AsyncMock(return_value=True)

    mock_track_manager.add_track = AsyncMock()

    result = await track_downloader.download_track(mock_track_obj, mock_album_obj)

    assert result.success is True
    assert result.skipped is False
    assert result.file_path == expected_path
    assert result.track == mock_track_obj

    track_downloader._get_track_path.assert_called_once_with(mock_track_obj, mock_album_obj)
    track_downloader._check_file_exists.assert_called_once_with(expected_path)
    track_downloader._check_track_availability.assert_called_once_with(mock_track_obj.id)
    track_downloader.client.get_stream_url.assert_called_once()
    track_downloader._download_file.assert_called_once()
    mock_track_manager.add_track.assert_called_once_with(mock_track_obj.id, expected_path)


@pytest.mark.asyncio
async def test_download_track_file_exists(track_downloader, base_settings):
    mock_artist = create_artist("art_exist", "Exist Artist")
    mock_album_obj = create_album("alb_exist", "Exist Album", [mock_artist])
    mock_track_obj = create_track("trk_exist", "Exist Track", [mock_artist], mock_album_obj)
    
    expected_path = base_settings.download_path / "Exist Artist" / "Exist Album" / "01 - Exist Track.flac"

    track_downloader._get_track_path = MagicMock(return_value=expected_path)
    track_downloader._check_file_exists = AsyncMock(return_value=(True, "File already exists"))
    track_downloader._download_file = AsyncMock()

    result = await track_downloader.download_track(mock_track_obj, mock_album_obj)

    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason == "File already exists"
    assert result.file_path == expected_path
    
    track_downloader.client.get_stream_url.assert_not_called()
    track_downloader._download_file.assert_not_called()
    track_downloader.track_manager.add_track.assert_not_called()


@pytest.mark.asyncio
async def test_download_track_unavailable(track_downloader, base_settings):
    mock_artist = create_artist("art_unavail", "Unavailable Artist")
    mock_album_obj = create_album("alb_unavail", "Unavailable Album", [mock_artist])
    mock_track_obj = create_track("trk_unavail", "Unavailable Track", [mock_artist], mock_album_obj)
    
    expected_path = base_settings.download_path / "Unavailable Artist" / "Unavailable Album" / "01 - Unavailable Track.flac"

    track_downloader._get_track_path = MagicMock(return_value=expected_path)
    track_downloader._check_file_exists = AsyncMock(return_value=(False, None))
    track_downloader._check_track_availability = AsyncMock(return_value=(False, "Track not available in region"))
    track_downloader._download_file = AsyncMock()

    result = await track_downloader.download_track(mock_track_obj, mock_album_obj)

    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason == "Track not available in region"
    
    track_downloader.client.get_stream_url.assert_not_called()
    track_downloader._download_file.assert_not_called()


@pytest.mark.asyncio
async def test_download_track_download_fails(track_downloader, base_settings, mock_track_manager):
    mock_artist = create_artist("art_fail", "Fail Artist")
    mock_album_obj = create_album("alb_fail", "Fail Album", [mock_artist])
    mock_track_obj = create_track("trk_fail", "Fail Track", [mock_artist], mock_album_obj)
    
    expected_path = base_settings.download_path / "Fail Artist" / "Fail Album" / "01 - Fail Track.flac"

    track_downloader._get_track_path = MagicMock(return_value=expected_path)
    track_downloader._check_file_exists = AsyncMock(return_value=(False, None))
    track_downloader._check_track_availability = AsyncMock(return_value=(True, None))
    
    mock_stream_url = MagicMock()
    mock_stream_url.url = "http://example.com/stream_fail"
    mock_stream_url.soundQuality = "LOSSLESS"
    track_downloader.client.get_stream_url = AsyncMock(return_value=mock_stream_url)
    
    track_downloader._download_file = AsyncMock(return_value=False)
    async def mock_download_file_effect(url, path, progress, retry_count=0):
        progress.error_message = "Simulated network error"
        return False
    track_downloader._download_file.side_effect = mock_download_file_effect


    result = await track_downloader.download_track(mock_track_obj, mock_album_obj)

    assert result.success is False
    assert result.skipped is False
    assert result.error_message == "Simulated network error"
    
    track_downloader._download_file.assert_called_once()
    mock_track_manager.add_track.assert_not_called()
