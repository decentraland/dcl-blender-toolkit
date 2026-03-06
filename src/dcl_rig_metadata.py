"""
Metadata and path helpers for the bundled Decentraland rig asset.
"""

import os

DCL_RIG_ASSET_NAME = "Avatar_File.blend"
DCL_RIG_SOURCE_URL = "https://raw.githubusercontent.com/decentraland/docs/main/creator/images/emotes/Avatar_File.blend"
DCL_RIG_DOCS_URL = "https://docs.decentraland.org/creator/wearables-and-emotes/emotes/creating-emotes/"
DCL_RIG_VERSION = "rig-1.0"


def get_assets_dir():
    """Return the add-on local assets directory."""
    return os.path.join(os.path.dirname(__file__), "assets")


def get_rig_blend_path():
    """Return the absolute path to the bundled DCL rig .blend file."""
    return os.path.join(get_assets_dir(), DCL_RIG_ASSET_NAME)
