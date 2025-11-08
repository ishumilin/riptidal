"""
API keys for Tidal API.

This module provides API keys for the Tidal API, along with information about
their capabilities and limitations.
"""

import json
import logging
import requests
from typing import Dict, List, Optional, Any

from riptidal.utils.logger import get_logger

# Default API keys JSON
__KEYS_JSON__ = '''
{
    "version": "1.0.1",
    "keys": [
        {
            "platform": "Fire TV",
            "formats": "Normal/High/HiFi(No Master)",
            "clientId": "OmDtrzFgyVVL6uW56OnFA2COiabqm",
            "clientSecret": "zxen1r3pO0hgtOC7j6twMo9UAqngGrmRiWpV7QC1zJ8=",
            "valid": "False",
            "from": "Fokka-Engineering (https://github.com/Fokka-Engineering/libopenTIDAL/blob/655528e26e4f3ee2c426c06ea5b8440cf27abc4a/README.md#example)"
        },
        {
            "platform": "Fire TV",
            "formats": "Master-Only(Else Error)",
            "clientId": "7m7Ap0JC9j1cOM3n",
            "clientSecret": "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY=",
            "valid": "True",
            "from": "Dniel97 (https://github.com/Dniel97/RedSea/blob/4ba02b88cee33aeb735725cb854be6c66ff372d4/config/settings.example.py#L68)"
        },
        {
            "platform": "Android TV",
            "formats": "Normal/High/HiFi(No Master)",
            "clientId": "Pzd0ExNVHkyZLiYN",
            "clientSecret": "W7X6UvBaho+XOi1MUeCX6ewv2zTdSOV3Y7qC3p3675I=",
            "valid": "False",
            "from": ""
        },
        {
            "platform": "TV",
            "formats": "Normal/High/HiFi/Master",
            "clientId": "8SEZWa4J1NVC5U5Y",
            "clientSecret": "owUYDkxddz+9FpvGX24DlxECNtFEMBxipU0lBfrbq60=",
            "valid": "False",
            "from": "morguldir (https://github.com/morguldir/python-tidal/commit/50f1afcd2079efb2b4cf694ef5a7d67fdf619d09)"
        },
        {
            "platform": "Android Auto",
            "formats": "Normal/High/HiFi/Master",
            "clientId": "zU4XHVVkc2tDPo4t",
            "clientSecret": "VJKhDFqJPqvsPVNBV6ukXTJmwlvbttP7wlMlrc72se4=",
            "valid": "True",
            "from": "1nikolas (https://github.com/yaronzz/Tidal-Media-Downloader/pull/840)"
        }
    ]
}
'''

__API_KEYS__ = json.loads(__KEYS_JSON__)

# Error key to return when an invalid index is requested
__ERROR_KEY__ = {
    'platform': 'None',
    'formats': '',
    'clientId': '',
    'clientSecret': '',
    'valid': 'False',
}


def get_num_keys() -> int:
    """Get the number of available API keys."""
    return len(__API_KEYS__['keys'])


def get_key(index: int) -> Dict[str, str]:
    """
    Get an API key by index.
    
    Args:
        index: Index of the key to get
        
    Returns:
        Dictionary containing key information
    """
    if index < 0 or index >= len(__API_KEYS__['keys']):
        return __ERROR_KEY__
    return __API_KEYS__['keys'][index]


def is_key_valid(index: int) -> bool:
    """
    Check if an API key is valid.
    
    Args:
        index: Index of the key to check
        
    Returns:
        True if the key is valid, False otherwise
    """
    key = get_key(index)
    return key['valid'] == 'True'


def get_all_keys() -> List[Dict[str, str]]:
    """
    Get all available API keys.
    
    Returns:
        List of dictionaries containing key information
    """
    return __API_KEYS__['keys']


def get_valid_indices() -> List[str]:
    """
    Get a list of valid key indices.
    
    Returns:
        List of valid key indices as strings
    """
    return [str(i) for i in range(len(__API_KEYS__['keys']))]


def get_version() -> str:
    """
    Get the version of the API keys.
    
    Returns:
        Version string
    """
    return __API_KEYS__['version']


def update_keys_from_gist() -> bool:
    """
    Update API keys from GitHub Gist.
    
    Returns:
        True if keys were updated, False otherwise
    """
    logger = get_logger(__name__)
    try:
        logger.info("Updating API keys from GitHub Gist...")
        response = requests.get('https://api.github.com/gists/48d01f5a24b4b7b37f19443977c22cd6')
        if response.status_code == 200:
            content = response.json()['files']['tidal-api-key.json']['content']
            global __API_KEYS__
            __API_KEYS__ = json.loads(content)
            logger.info(f"API keys updated to version {get_version()}")
            return True
        else:
            logger.warning(f"Failed to update API keys: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error updating API keys: {str(e)}")
        return False


# Try to update keys from GitHub Gist on module import
try:
    update_keys_from_gist()
except:
    pass
