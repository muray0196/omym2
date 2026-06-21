"""
Summary: Centralizes shared implementation constants.
Why: Keeps tunable literals out of domain and shared helper logic.
"""

from __future__ import annotations

from typing import Final

CURRENT_DIRECTORY_REFERENCE: Final = "."
LOGICAL_PATH_SEPARATOR: Final = "/"
PARENT_DIRECTORY_REFERENCE: Final = ".."
UUID_VERSION: Final = 7

CONFIG_VERSION: Final = 1  # supported user config schema version
DEFAULT_COMMAND_MODE: Final = "plan_first"  # initial plan creation mode for mutating commands
DEFAULT_ADD_AUTO_APPLY: Final = False  # add command auto-apply default
DEFAULT_ORGANIZE_AUTO_APPLY: Final = False  # organize command auto-apply default
DEFAULT_ORGANIZE_ONLY_MISPLACED: Final = True  # organize scans only misplaced files by default
DEFAULT_REFRESH_AUTO_APPLY: Final = False  # refresh command auto-apply default
DEFAULT_PATH_POLICY_TEMPLATE: Final = (
    "{album_artist}/{year}_{album}/{disc}-{track}_{title}.{ext}"  # canonical path template
)
DEFAULT_UNKNOWN_ARTIST: Final = "Unknown Artist"  # fallback artist text for path generation
DEFAULT_UNKNOWN_ALBUM: Final = "Unknown Album"  # fallback album text for path generation
DEFAULT_PATH_POLICY_SANITIZE: Final = True  # sanitize metadata text before it becomes path text
DEFAULT_MAX_FILENAME_LENGTH: Final = 180  # maximum generated path component length, characters
DEFAULT_METADATA_PREFER_ALBUM_ARTIST: Final = True  # prefer album artist when metadata provides it
DEFAULT_METADATA_REQUIRE_TITLE: Final = True  # require title metadata during plan creation
DEFAULT_METADATA_REQUIRE_ARTIST: Final = True  # require artist metadata during plan creation
DEFAULT_METADATA_REQUIRE_ALBUM: Final = False  # require album metadata during plan creation
DEFAULT_COLLISION_ON_TARGET_EXISTS: Final = "conflict"  # target collision policy name
DEFAULT_COLLISION_ON_DUPLICATE_HASH: Final = "skip"  # duplicate content policy name
DEFAULT_COLLISION_ON_MISSING_METADATA: Final = "block"  # missing metadata policy name
DEFAULT_UI_THEME: Final = "system"  # default UI color mode
DEFAULT_UI_SHOW_ADVANCED_SETTINGS: Final = False  # default advanced settings visibility
CONTENT_FINGERPRINT_ALGORITHM: Final = "sha256"  # content fingerprint hash algorithm
METADATA_FINGERPRINT_ALGORITHM: Final = "sha256"  # metadata fingerprint hash algorithm
METADATA_FINGERPRINT_ENCODING: Final = "utf-8"  # metadata fingerprint payload encoding
METADATA_FINGERPRINT_JSON_ITEM_SEPARATOR: Final = ","  # canonical JSON item separator
METADATA_FINGERPRINT_JSON_KEY_SEPARATOR: Final = ":"  # canonical JSON key separator
PATH_EXTENSION_PREFIX: Final = "."  # separator before generated file extensions
PATH_POLICY_EXTENSION_PLACEHOLDER: Final = "{ext}"  # required template token for the source file extension
PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT: Final = "_"  # replacement for empty generated path components
PATH_POLICY_TRACK_NUMBER_WIDTH: Final = 2  # zero-padding width for generated track numbers
PATH_POLICY_UNSAFE_CHARACTERS: Final = '<>:"\\|?*/'  # characters replaced in metadata path components
