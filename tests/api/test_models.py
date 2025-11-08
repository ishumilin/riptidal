import pytest
from pydantic import ValidationError

from riptidal.api.models import Artist, Album, Video, ResourceType, StreamQuality, VideoQuality, Track as ApiTrack

# Tests for Artist model
def test_artist_valid_data_str_id():
    data = {"id": "123", "name": "Test Artist"}
    artist = Artist(**data)
    assert artist.id == "123"
    assert artist.name == "Test Artist"
    assert artist.picture is None

def test_artist_valid_data_int_id():
    data = {"id": 123, "name": "Test Artist Int ID"}
    artist = Artist(**data)
    assert artist.id == "123"
    assert artist.name == "Test Artist Int ID"

def test_artist_optional_fields():
    data = {
        "id": "789",
        "name": "Full Artist",
        "picture": "http://example.com/pic.jpg",
        "type": "ARTIST",
        "url": "http://example.com/artist/789"
    }
    artist = Artist(**data)
    assert artist.picture == "http://example.com/pic.jpg"
    assert artist.type == "ARTIST"
    assert artist.url == "http://example.com/artist/789"

def test_artist_missing_id():
    data = {"name": "Artist No ID"}
    with pytest.raises(ValidationError) as excinfo:
        Artist(**data)
    assert "id" in str(excinfo.value).lower()
    assert "field required" in str(excinfo.value).lower()


def test_artist_missing_name():
    data = {"id": "456"}
    with pytest.raises(ValidationError) as excinfo:
        Artist(**data)
    assert "name" in str(excinfo.value).lower()
    assert "field required" in str(excinfo.value).lower()

def test_artist_id_none():
    data = {"id": None, "name": "Artist None ID"}
    with pytest.raises(ValidationError) as excinfo:
        Artist(**data)
    assert "id" in str(excinfo.value).lower()
    assert "input should be a valid string" in str(excinfo.value).lower()
    assert "input_value=none" in str(excinfo.value).lower()

# Tests for Video model
def test_video_valid_data():
    artist_data = {"id": "1", "name": "Video Artist"}
    album_data = {"id": "10", "title": "Video Album", "artists": [artist_data]}
    data = {
        "id": "101",
        "title": "Test Video",
        "duration": 180,
        "quality": "1080P",
        "explicit": False,
        "artist": artist_data,
        "artists": [artist_data],
        "album": album_data,
        "version": "Director's Cut",
        "url": "http://example.com/video/101"
    }
    video = Video(**data)
    assert video.id == "101"
    assert video.title == "Test Video"
    assert video.album.id == "10"
    assert video.album.title == "Video Album"
    assert video.artists[0].name == "Video Artist"

def test_video_id_int():
    data = {"id": 202, "title": "Video Int ID"}
    video = Video(**data)
    assert video.id == "202"

def test_video_album_validator_none():
    data = {"id": "303", "title": "Video No Album", "album": None}
    video = Video(**data)
    assert video.album is None

def test_video_album_validator_empty_dict():
    data = {"id": "404", "title": "Video Empty Dict Album", "album": {}}
    video = Video(**data)
    assert video.album is None

def test_video_album_validator_valid_album():
    album_data = {"id": "20", "title": "Another Video Album"}
    data = {"id": "505", "title": "Video With Album", "album": album_data}
    video = Video(**data)
    assert video.album is not None
    assert video.album.id == "20"
    assert video.album.title == "Another Video Album"

def test_video_missing_id():
    data = {"title": "Video No ID"}
    with pytest.raises(ValidationError):
        Video(**data)

def test_video_missing_title():
    data = {"id": "606"}
    with pytest.raises(ValidationError):
        Video(**data)

def test_resource_type_enum():
    assert ResourceType.ALBUM.value == "ALBUM"
    assert ResourceType.TRACK == "TRACK"

def test_stream_quality_enum():
    assert StreamQuality.HI_RES_LOSSLESS == "HI_RES_LOSSLESS"

def test_video_quality_enum():
    assert VideoQuality.P1080 == "1080"
    assert VideoQuality.MAX.value == "MAX"


# Tests for Track model
def test_track_valid_data():
    artist_data = {"id": "art1", "name": "Track Artist"}
    album_data = {"id": "alb1", "title": "Track Album", "artists": [artist_data]}
    data = {
        "id": "trk1",
        "title": "Test Track",
        "duration": 245000,
        "trackNumber": 1,
        "volumeNumber": 1,
        "explicit": True,
        "audioQuality": "LOSSLESS",
        "artist": artist_data,
        "artists": [artist_data, {"id": "art2", "name": "Featured Artist"}],
        "album": album_data,
        "version": "Remix"
    }
    track = ApiTrack(**data)
    assert track.id == "trk1"
    assert track.title == "Test Track"
    assert track.duration == 245000
    assert track.audioQuality == "LOSSLESS"
    assert track.version == "Remix"
    assert track.album.title == "Track Album"
    assert len(track.artists) == 2

def test_track_id_int():
    data = {"id": 987, "title": "Track Int ID"}
    track = ApiTrack(**data)
    assert track.id == "987"

def test_track_formatted_title():
    track_no_version = ApiTrack(id="t1", title="Title Only")
    assert track_no_version.formatted_title == "Title Only"

    track_with_version = ApiTrack(id="t2", title="Title With Version", version="Radio Edit")
    assert track_with_version.formatted_title == "Title With Version (Radio Edit)"

def test_track_duration_formatted():
    track1 = ApiTrack(id="d1", title="Dur1", duration=185000)
    assert track1.duration_formatted == "03:05"

    track2 = ApiTrack(id="d2", title="Dur2", duration=59000)
    assert track2.duration_formatted == "00:59"
    
    track3 = ApiTrack(id="d3", title="Dur3", duration=3600000)
    assert track3.duration_formatted == "60:00"

    track4 = ApiTrack(id="d4", title="Dur4", duration=None)
    assert track4.duration_formatted == "00:00"
    
    track5 = ApiTrack(id="d5", title="Dur5", duration=0)
    assert track5.duration_formatted == "00:00"


def test_track_artist_names():
    artist1 = Artist(id="a1", name="Artist One")
    artist2 = Artist(id="a2", name="Artist Two")

    track_multi = ApiTrack(id="tn1", title="Multi", artist=artist1, artists=[artist1, artist2])
    assert track_multi.artist_names == "Artist One, Artist Two"

    track_single_primary = ApiTrack(id="tn2", title="SingleP", artist=artist1)
    assert track_single_primary.artist_names == "Artist One"
    
    track_single_list = ApiTrack(id="tn3", title="SingleL", artists=[artist1])
    assert track_single_list.artist_names == "Artist One"

    track_no_artist = ApiTrack(id="tn4", title="NoArtist")
    assert track_no_artist.artist_names == "Unknown Artist"
    
    track_empty_list_primary = ApiTrack(id="tn5", title="EmptyListP", artist=artist1, artists=[])
    assert track_empty_list_primary.artist_names == "Artist One"
