from riptidal.utils import paths
from riptidal.utils.paths import get_default_download_dir, get_config_dir, get_data_dir, get_cache_dir # Corrected import
from unittest.mock import patch
from pathlib import Path
import pytest # Added pytest import

# Fixture for default paths generation test
@pytest.fixture
def temp_project_root(tmp_path):
    project_root = tmp_path / "riptidal_project"
    project_root.mkdir()
    return project_root

@patch('riptidal.utils.paths.get_project_root')
def test_default_paths_generation(mock_get_project_root, temp_project_root):
    mock_get_project_root.return_value = temp_project_root

    assert get_default_download_dir() == temp_project_root / "Downloads" # Changed to get_default_download_dir
    assert get_config_dir() == temp_project_root / ".config" # Changed to get_config_dir
    assert get_data_dir() == temp_project_root / ".data"     # Changed to get_data_dir
    assert get_cache_dir() == temp_project_root / ".cache"   # Changed to get_cache_dir


def test_sanitize_filename_basic():
    assert paths.sanitize_filename("Valid Name 123.mp3") == "Valid Name 123.mp3"
    assert paths.sanitize_filename("Invalid<>Chars:*?.mp3") == "Invalid__Chars___.mp3"
    assert paths.sanitize_filename("Another / Test \\ With | Bad : Chars.txt") == "Another _ Test _ With _ Bad _ Chars.txt"

def test_sanitize_filename_empty():
    assert paths.sanitize_filename("") == "unnamed"

def test_sanitize_filename_only_invalid():
    assert paths.sanitize_filename("<>:\"/\\|?*") == "_________"

def test_sanitize_filename_non_latin():
    assert paths.sanitize_filename("Привет мир.mp3") == "Привет мир.mp3"  # Cyrillic
    assert paths.sanitize_filename("こんにちは.mp3") == "こんにちは.mp3"  # Japanese
    assert paths.sanitize_filename("你好世界.aac") == "你好世界.aac" # Chinese
    assert paths.sanitize_filename("مرحبا بالعالم.flac") == "مرحبا بالعالم.flac"

def test_sanitize_filename_with_control_chars():
    # ASCII control characters 0-31 and 127
    assert paths.sanitize_filename("File\x08With\x0BSome\x7FControls.txt") == "FileWithSomeControls.txt"

def test_sanitize_filename_leading_trailing_spaces():
    assert paths.sanitize_filename("  leading and trailing spaces  .mp3") == "leading and trailing spaces  .mp3"

def test_sanitize_filename_dots():
    assert paths.sanitize_filename("file.name.with.dots.ext") == "file.name.with.dots.ext"
    assert paths.sanitize_filename("...leadingdots.txt") == "leadingdots.txt"
    # Windows might have issues with filenames ending in a dot.
    assert paths.sanitize_filename("trailingdot.") == "trailingdot"
