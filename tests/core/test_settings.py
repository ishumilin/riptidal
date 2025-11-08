import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from riptidal.core.settings import Settings, load_settings, save_settings
from riptidal.utils.paths import get_project_root


def test_load_settings_file_does_not_exist(tmp_path):
    """Test loading settings when the settings file doesn't exist."""
    with patch('riptidal.utils.paths.get_project_root', return_value=tmp_path):
        settings = load_settings()
        assert isinstance(settings, Settings)
        assert settings.download_path == tmp_path / "Downloads"
        assert settings.audio_quality.value == "HIGH"
        assert settings.video_quality.value == "720"

def test_save_and_load_settings(tmp_path):
    """Test saving settings and then loading them back."""
    custom_settings_data = {
        "user_id": "test_user",
        "auth_token": "test_auth_token",
        "refresh_token": "test_refresh_token",
        "token_expiry": 1234567890,
        "country_code": "US",
        "api_key_index": 1,
        "audio_quality": "HIFI",
        "video_quality": "720",
        "download_path": str(tmp_path / "MyCustomDownloads"),
        "track_path_format": "{artist_name}/{album_name}/{title_only}",
        "playlist_path_format": "MyPlaylists/{playlist_name}",
        "download_full_albums": True,
        "create_m3u_playlists": False,
        "quality_fallback": False,
        "enable_playlists": False,
        "connection_timeout": 60,
        "retry_attempts": 5,
        "retry_delay": 10,
    }
    settings_to_save = Settings(**custom_settings_data)

    with patch('riptidal.utils.paths.get_project_root', return_value=tmp_path):
        config_dir = tmp_path / ".config"
        
        save_settings(settings_to_save)
        
        settings_file = config_dir / "settings.json"
        assert settings_file.exists()
        with open(settings_file, 'r') as f:
            saved_data = json.load(f)
        
        expected_saved_data = settings_to_save.model_dump(mode='json')
        if "download_path" in expected_saved_data and isinstance(expected_saved_data["download_path"], Path):
            expected_saved_data["download_path"] = str(expected_saved_data["download_path"])
        assert saved_data == expected_saved_data

        loaded_settings = load_settings()
    
    assert loaded_settings.user_id == "test_user"
    assert loaded_settings.audio_quality.value == "HIFI"
    assert loaded_settings.video_quality.value == "720"
    assert loaded_settings.download_path == tmp_path / "MyCustomDownloads"
    assert loaded_settings.track_path_format == "{artist_name}/{album_name}/{title_only}"
    assert loaded_settings.playlist_path_format == "MyPlaylists/{playlist_name}"
    assert loaded_settings.download_full_albums is True
    assert loaded_settings.create_m3u_playlists is False
    assert loaded_settings.quality_fallback is False
    assert loaded_settings.enable_playlists is False
    assert loaded_settings.connection_timeout == 60
    assert loaded_settings.retry_attempts == 5
    assert loaded_settings.retry_delay == 10
    assert loaded_settings.auth_token == "test_auth_token"
    assert loaded_settings.country_code == "US"
    assert loaded_settings.api_key_index == 1


def test_load_settings_with_partial_file(tmp_path):
    """Test loading settings when the file exists but is missing some fields."""
    partial_settings_data = {
        "audio_quality": "MQA", # This is an invalid enum value
        "download_path": str(tmp_path / "PartialDownloads")
    }
    
    with patch('riptidal.utils.paths.get_project_root', return_value=tmp_path):
        config_dir = tmp_path / ".config"
        config_dir.mkdir(parents=True, exist_ok=True)
        settings_file = config_dir / "settings.json"
        with open(settings_file, 'w') as f:
            json.dump(partial_settings_data, f)
            
        settings = load_settings()

    # If "MQA" is invalid, load_settings returns default Settings()
    assert settings.audio_quality.value == "HIGH"
    assert settings.download_path == tmp_path / "Downloads"
    assert settings.video_quality.value == "720"


def test_settings_model_defaults(tmp_path):
    """Test that the Pydantic model provides correct defaults."""
    with patch('riptidal.utils.paths.get_project_root', return_value=tmp_path):
        settings = Settings()
        assert settings.download_path == tmp_path / "Downloads"
        assert settings.track_path_format == "{artist_name}/{album_name}/{track_number} - {track_title}"
        assert settings.audio_quality.value == "HIGH"
        assert settings.video_quality.value == "720"
        assert settings.download_full_albums is False
        assert settings.playlist_path_format == "Playlists/{playlist_name}"
        assert settings.quality_fallback is True
        assert settings.enable_playlists is True
        assert settings.create_m3u_playlists is True
        assert settings.connection_timeout == 30
        assert settings.api_key_index == 4


@patch('riptidal.utils.paths.get_project_root')
def test_settings_path_validators(mock_get_project_root, tmp_path):
    mock_get_project_root.return_value = tmp_path

    settings1 = Settings(download_path=str(tmp_path / "test_downloads"))
    assert settings1.download_path == tmp_path / "test_downloads"

    settings2 = Settings(download_path="") 
    assert settings2.download_path == Path(".")
    
    settings3 = Settings(track_path_format="{artist}/{title}")
    assert settings3.track_path_format == "{artist}/{title}"
    
    with pytest.raises(ValueError, match="Path format cannot be empty"):
        Settings(track_path_format="")

    settings4_default = Settings()
    assert settings4_default.track_path_format == "{artist_name}/{album_name}/{track_number} - {track_title}"


    with pytest.raises(ValueError, match="Path format cannot be empty"):
        Settings(playlist_path_format="")

    settings5_default = Settings()
    assert settings5_default.playlist_path_format == "Playlists/{playlist_name}"
