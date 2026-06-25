"""
Summary: Centralizes shared implementation constants.
Why: Keeps tunable literals out of domain and shared helper logic.
"""

from __future__ import annotations

from typing import Final

APP_DIRECTORY_NAME: Final = "omym2"  # application root directory under the user home
CONFIG_DIRECTORY_NAME: Final = "config"  # user config directory under the application root
CONFIG_FILE_ENCODING: Final = "utf-8"  # TOML config file encoding
CONFIG_FILE_NAME: Final = "config.toml"  # TOML settings file name
CURRENT_DIRECTORY_REFERENCE: Final = "."
DATA_DIRECTORY_NAME: Final = ".data"  # internal data directory under the application root
SQLITE_DATABASE_FILE_NAME: Final = "omym2.sqlite3"  # SQLite database file name
WEB_DEFAULT_HOST: Final = "127.0.0.1"  # local Web UI bind host
WEB_DEFAULT_PORT: Final = 8765  # local Web UI bind port
WEB_APP_TITLE: Final = "OMYM2 Settings"  # local Web UI application title
WEB_ROOT_ROUTE: Final = "/"  # local Web UI root path
WEB_SETTINGS_ROUTE: Final = "/settings"  # local Web UI settings path
WEB_STATIC_ROUTE: Final = "/static"  # local Web UI static asset mount path
WEB_STATIC_DIRECTORY_NAME: Final = "static"  # package directory for local Web UI static assets
WEB_TEMPLATE_DIRECTORY_NAME: Final = "templates"  # package directory for local Web UI templates
WEB_SETTINGS_TEMPLATE_NAME: Final = "settings.html"  # Jinja template for the settings screen
WEB_URL_SCHEME: Final = "http"  # scheme used for the local Web UI browser URL
LOGICAL_PATH_SEPARATOR: Final = "/"
PARENT_DIRECTORY_REFERENCE: Final = ".."
UUID_VERSION: Final = 7
PLAN_ACTION_SORT_ORDER_START: Final = 1  # first review-order value stored for PlanActions
PLAN_ACTION_SORT_ORDER_STEP: Final = 1  # increment between adjacent PlanAction sort orders
FILE_EVENT_SEQUENCE_START: Final = 1  # first durable mutation event sequence number in a Run
FILE_EVENT_SEQUENCE_STEP: Final = 1  # increment between adjacent durable mutation events

ALLOWED_COMMAND_MODES: Final = frozenset({"plan_first"})  # supported command default_mode values
ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES: Final = frozenset({"skip"})  # duplicate content decisions
ALLOWED_COLLISION_MISSING_METADATA_POLICIES: Final = frozenset({"block"})  # missing metadata decisions
ALLOWED_COLLISION_TARGET_EXISTS_POLICIES: Final = frozenset({"conflict"})  # target collision decisions
ALLOWED_UI_THEMES: Final = frozenset({"system", "light", "dark"})  # supported local UI themes
CONFIG_VERSION: Final = 1  # supported user config schema version
DEFAULT_COMMAND_MODE: Final = "plan_first"  # initial plan creation mode for mutating commands
DEFAULT_ADD_AUTO_APPLY: Final = False  # add command auto-apply default
DEFAULT_ORGANIZE_AUTO_APPLY: Final = False  # organize command auto-apply default
DEFAULT_ORGANIZE_ONLY_MISPLACED: Final = True  # organize scans only misplaced files by default
DEFAULT_REFRESH_AUTO_APPLY: Final = False  # refresh command auto-apply default
DEFAULT_PATH_POLICY_TEMPLATE: Final = (
    "{album_artist}/{year}_{album}/{disc}-{track}_{title}"  # canonical path stem template
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
CONTENT_HASH_READ_CHUNK_SIZE_BYTES: Final = 1_048_576  # file hash read chunk size, bytes, positive
CONFIG_FINGERPRINT_ALGORITHM: Final = "sha256"  # config fingerprint hash algorithm
CONFIG_FINGERPRINT_ENCODING: Final = "utf-8"  # config fingerprint payload encoding
CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR: Final = ","  # canonical JSON item separator
CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR: Final = ":"  # canonical JSON key separator
METADATA_FINGERPRINT_ALGORITHM: Final = "sha256"  # metadata fingerprint hash algorithm
METADATA_FINGERPRINT_ENCODING: Final = "utf-8"  # metadata fingerprint payload encoding
METADATA_FINGERPRINT_JSON_ITEM_SEPARATOR: Final = ","  # canonical JSON item separator
METADATA_FINGERPRINT_JSON_KEY_SEPARATOR: Final = ":"  # canonical JSON key separator
PERSISTED_JSON_ITEM_SEPARATOR: Final = ","  # compact JSON item separator for SQLite payloads
PERSISTED_JSON_KEY_SEPARATOR: Final = ":"  # compact JSON key separator for SQLite payloads
PATH_EXTENSION_PREFIX: Final = "."  # separator before generated file extensions
PATH_POLICY_ALLOWED_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "album_artist",
    "album",
    "disc",
    "track",
    "title",
    "artist",
    "year",
)  # placeholders allowed in path policy stem templates
PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT: Final = "_"  # replacement for empty generated path components
PATH_POLICY_TRACK_NUMBER_WIDTH: Final = 2  # zero-padding width for generated track numbers
PATH_POLICY_UNSAFE_CHARACTERS: Final = '<>:"\\|?*/'  # characters replaced in metadata path components
PATH_POLICY_PREVIEW_TITLE: Final = "Example Song"  # sample title shown in settings preview
PATH_POLICY_PREVIEW_ARTIST: Final = "Aimer"  # sample artist shown in settings preview
PATH_POLICY_PREVIEW_ALBUM: Final = "Example Album"  # sample album shown in settings preview
PATH_POLICY_PREVIEW_ALBUM_ARTIST: Final = "Aimer"  # sample album artist shown in settings preview
PATH_POLICY_PREVIEW_YEAR: Final = 2024  # sample release year shown in settings preview
PATH_POLICY_PREVIEW_DISC_NUMBER: Final = 1  # sample disc number shown in settings preview
PATH_POLICY_PREVIEW_TRACK_NUMBER: Final = 3  # sample track number shown in settings preview
PATH_POLICY_PREVIEW_FILE_EXTENSION: Final = ".FLAC"  # sample source suffix shown in settings preview
SQLITE_CONNECTION_TIMEOUT_SECONDS: Final = 30.0  # SQLite connection busy timeout, seconds
SQLITE_MIGRATION_FILE_ENCODING: Final = "utf-8"  # SQLite migration resource encoding
SQLITE_MIGRATION_FILE_EXTENSION: Final = ".sql"  # migration resource file extension
SUPPORTED_MUSIC_FILE_EXTENSIONS: Final = frozenset(
    {
        ".aac",
        ".aiff",
        ".ape",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".opus",
        ".wav",
        ".wv",
    }
)  # suffixes treated as music files during read-only scans
