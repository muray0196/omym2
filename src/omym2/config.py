"""
Summary: Centralizes shared implementation constants.
Why: Keeps tunable literals out of domain and shared helper logic.
"""

from __future__ import annotations

from typing import Final

CONFIG_REVISION_ALGORITHM: Final = "sha256"  # opaque raw Config revision digest algorithm
CONFIG_REVISION_PREFIX: Final = "v1"  # opaque raw Config revision encoding version
CONFIG_SNAPSHOT_READ_MAX_ATTEMPTS: Final = 3  # retries when Config changes during one snapshot read, attempts, >= 1
CONFIG_DIRECTORY_NAME: Final = ".config"  # user config directory under the application root
CONFIG_FILE_ENCODING: Final = "utf-8"  # TOML config file encoding
CONFIG_FILE_NAME: Final = "config.toml"  # TOML settings file name
CURRENT_DIRECTORY_REFERENCE: Final = "."
DATA_DIRECTORY_NAME: Final = ".data"  # internal data directory under the application root
EXCLUSIVE_OPERATION_LOCK_FILE_NAME: Final = "exclusive-operation.lock"  # shared cross-process mutation lock file name
SQLITE_DATABASE_FILE_NAME: Final = "omym2.sqlite3"  # SQLite database file name
BENCHMARK_DEFAULT_TRACK_COUNT: Final = 100  # default synthetic benchmark size, tracks, >= 1
BENCHMARK_DEFAULT_FILE_SIZE_BYTES: Final = 1_048_576  # default synthetic file size, bytes, >= 4096
BENCHMARK_DEFAULT_TRACKS_PER_ALBUM: Final = 10  # default synthetic album shape, tracks per album, >= 1
BENCHMARK_MUTATION_SENTINEL_BYTES: Final = 1  # payload appended after tag mutation, bytes, >= 1
BENCHMARK_MIN_TRACK_COUNT: Final = 1  # minimum synthetic benchmark size, tracks, >= 1
BENCHMARK_MIN_FILE_SIZE_BYTES: Final = 4_096  # minimum tagged synthetic FLAC size, bytes, >= 4096
BENCHMARK_MIN_TRACKS_PER_ALBUM: Final = 1  # minimum synthetic album shape, tracks per album, >= 1
BENCHMARK_FILE_WRITE_CHUNK_SIZE_BYTES: Final = 1_048_576  # bounded fixture write chunk, bytes, >= 1
WEB_DEFAULT_HOST: Final = "127.0.0.1"  # local Web UI bind host
WEB_DEFAULT_PORT: Final = 8765  # local Web UI bind port
WEB_APP_TITLE: Final = "OMYM2"  # local Web UI application title
DESKTOP_SUPPORTED_PLATFORM = "win32"  # supported desktop runtime platform, sys.platform value, Windows only
DESKTOP_APPLICATION_DIRECTORY_NAME = "OMYM2"  # per-user desktop application directory name
DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE = "LOCALAPPDATA"  # Windows per-user local application-data variable
DESKTOP_LOG_DIRECTORY_NAME = "logs"  # desktop diagnostic directory under the internal data directory
DESKTOP_LOG_FILE_NAME = "omym2-desktop.log"  # desktop diagnostic log file name
DESKTOP_LOG_MAX_BYTES = 5_242_880  # maximum desktop log file size before rotation, bytes, >= 1
DESKTOP_LOG_BACKUP_COUNT = 3  # retained rotated desktop log files, files, >= 1
DESKTOP_LOG_LEVEL = "INFO"  # minimum persisted desktop log severity
DESKTOP_LOG_ENCODING = "utf-8"  # desktop diagnostic log text encoding
DESKTOP_LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"  # desktop log record format
DESKTOP_LOOPBACK_HOST = "127.0.0.1"  # desktop server bind host, loopback only
DESKTOP_EPHEMERAL_PORT = 0  # operating-system-selected desktop server port, exactly 0
DESKTOP_READINESS_MAX_ATTEMPTS = 200  # maximum Bootstrap readiness probes, attempts, >= 1
DESKTOP_READINESS_INTERVAL_SECONDS = 0.05  # delay between desktop readiness probes, seconds, > 0
DESKTOP_READINESS_TIMEOUT_SECONDS = 0.5  # timeout for one desktop readiness probe, seconds, > 0
DESKTOP_SERVER_THREAD_NAME = "omym2-desktop-server"  # background Uvicorn thread name
DESKTOP_WINDOW_TITLE = "OMYM2"  # native desktop window title
DESKTOP_WINDOW_WIDTH = 1440  # initial desktop window width, pixels, >= minimum width
DESKTOP_WINDOW_HEIGHT = 900  # initial desktop window height, pixels, >= minimum height
DESKTOP_WINDOW_MIN_WIDTH = 1024  # minimum desktop window width, pixels, >= supported Web viewport
DESKTOP_WINDOW_MIN_HEIGHT = 700  # minimum desktop window height, pixels, >= 1
DESKTOP_WINDOW_BACKGROUND_COLOR = "#07080a"  # native window background matching the Web canvas before paint
DESKTOP_WINDOW_RESIZABLE = True  # allow the native desktop window to resize
DESKTOP_WINDOW_MAXIMIZED = False  # open the native desktop window without maximizing it
DESKTOP_WEBVIEW_BACKEND = "edgechromium"  # required Windows native WebView backend
DESKTOP_WEBVIEW_PRIVATE_MODE = True  # avoid persistent browser cookies and local storage
DESKTOP_WEBVIEW_CONTENT_LOADED_LOG_MARKER = "Desktop WebView content loaded"  # exact post-navigation smoke marker
DESKTOP_WEBVIEW_CONTENT_LOAD_TIMEOUT_SECONDS = 30.0  # maximum wait for WebView document load, seconds, > 0
DESKTOP_WEBVIEW2_ENVIRONMENT_OVERRIDE_PREFIXES = (  # inherited WebView2 variables rejected before native startup
    "COREWEBVIEW2_",
    "WEBVIEW2_",
)
DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT = (  # administrative WebView2 loader policy root checked in both supported hives
    r"SOFTWARE\Policies\Microsoft\Edge\WebView2"
)
DESKTOP_WEBVIEW2_POLICY_NAMES = (  # policies capable of changing runtime selection, storage, or browser arguments
    "AdditionalBrowserArguments",
    "BrowserExecutableFolder",
    "ChannelSearchKind",
    "ReleaseChannels",
    "UserDataFolder",
)
DESKTOP_WEBVIEW2_POLICY_APPLICATION_ONLY_NAMES = (  # policies for which WebView2 does not accept the wildcard AppId
    "UserDataFolder",
)
DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID = "*"  # policy value name applying to every WebView2 host
DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY = (
    r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"  # .NET Framework registry key required by pywebview WinForms
)
DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE = "Release"  # installed .NET Framework release registry value
DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE = 394_802  # minimum .NET Framework 4.6.2 release required by pywebview
DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"  # 64-bit Evergreen WebView2 registry key
DESKTOP_WEBVIEW2_USER_REGISTRY_KEY = r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"  # per-user Evergreen WebView2 registry key
DESKTOP_WEBVIEW2_REGISTRY_VERSION_VALUE = "pv"  # Evergreen WebView2 installed-version registry value
DESKTOP_WEBVIEW2_MINIMUM_VERSION = (146, 0, 3856, 49)  # minimum Runtime for pywebview's bundled SDK 1.0.3856.49
DESKTOP_SUCCESS_EXIT_CODE = 0  # successful desktop process exit code
DESKTOP_FAILURE_EXIT_CODE = 1  # fatal desktop startup or runtime exit code
DESKTOP_ERROR_DIALOG_FLAGS = 0x10  # Windows MessageBox error-icon flags, MB_ICONERROR
WEB_CSRF_TOKEN_BYTES: Final = 32  # random bytes used for local Web UI save-token generation
WEB_CSRF_HEADER_NAME: Final = "X-OMYM2-CSRF-Token"  # header required for state-changing Web API saves
WEB_ROOT_ROUTE: Final = "/"  # local Web UI root path
WEB_SETTINGS_ROUTE: Final = "/settings"  # local Web UI settings SPA path
WEB_API_PREFIX: Final = "/api"  # local Web UI JSON API path prefix
WEB_API_BOOTSTRAP_ROUTE: Final = "/api/bootstrap"  # bundled Web UI Bootstrap JSON API path
WEB_API_SETTINGS_ROUTE: Final = "/api/settings"  # Settings edit and atomic save JSON API path
WEB_API_SETTINGS_VALIDATE_ROUTE: Final = "/api/settings/validate"  # Settings candidate validation JSON API path
WEB_API_SETTINGS_PREVIEW_ROUTE: Final = "/api/settings/preview"  # draft PathPolicy preview JSON API path
WEB_API_SETTINGS_ARTIST_IDS_ROUTE: Final = (
    "/api/settings/artist-ids/generate"  # draft-only artist-ID generation JSON API path
)
WEB_API_PLANS_ROUTE: Final = "/api/plans"  # read-only Plan browse JSON API path
WEB_API_PLAN_DETAIL_ROUTE: Final = "/api/plans/{plan_id}"  # Plan detail JSON API path
WEB_API_PLAN_ACTIONS_ROUTE: Final = "/api/plans/{plan_id}/actions"  # PlanAction browse JSON API path
WEB_API_PLAN_FACETS_ROUTE: Final = "/api/plans/{plan_id}/facets"  # PlanAction facet JSON API path
WEB_API_PLAN_GROUPS_ROUTE: Final = "/api/plans/{plan_id}/groups"  # PlanAction group JSON API path
WEB_API_ADD_PLAN_ROUTE: Final = "/api/plans/add"  # durable Add Plan operation JSON API path
WEB_API_ORGANIZE_PLAN_ROUTE: Final = "/api/plans/organize"  # durable Organize Plan operation JSON API path
WEB_API_REFRESH_PLAN_ROUTE: Final = "/api/plans/refresh"  # durable Refresh Plan operation JSON API path
WEB_API_APPLY_PLAN_ROUTE: Final = "/api/plans/{plan_id}/apply"  # durable atomic-claim Apply operation JSON API path
WEB_API_CANCEL_PLAN_ROUTE: Final = "/api/plans/{plan_id}/cancel"  # synchronous ready-Plan cancellation JSON API path
WEB_API_CHECK_RUN_ROUTE: Final = "/api/check/run"  # durable persisted Check operation JSON API path
WEB_API_OPERATION_ROUTE: Final = "/api/operations/{operation_id}"  # durable Operation polling JSON API path
WEB_IDEMPOTENCY_HEADER_NAME: Final = "Idempotency-Key"  # UUID header required to start durable Operations
WEB_API_TRACKS_ROUTE: Final = "/api/tracks"  # read-only Track browse JSON API path
WEB_API_TRACK_DETAIL_ROUTE: Final = "/api/tracks/{track_id}"  # Track detail JSON API path
WEB_API_TRACK_FACETS_ROUTE: Final = "/api/tracks/facets"  # Track status facet JSON API path
WEB_API_TRACK_GROUPS_ROUTE: Final = "/api/tracks/groups"  # Track hierarchy group JSON API path
WEB_API_LIBRARIES_ROUTE: Final = "/api/libraries"  # Library browse JSON API path
WEB_API_LIBRARY_DETAIL_ROUTE: Final = "/api/libraries/{library_id}"  # Library detail JSON API path
WEB_API_CHECK_ROUTE: Final = "/api/check"  # persisted CheckIssue browse JSON API path
WEB_API_CHECK_FACETS_ROUTE: Final = "/api/check/facets"  # persisted CheckIssue facet JSON API path
WEB_API_CHECK_GROUPS_ROUTE: Final = "/api/check/groups"  # persisted CheckIssue group JSON API path
WEB_API_HISTORY_ROUTE: Final = "/api/history"  # Run history browse JSON API path
WEB_API_HISTORY_FACETS_ROUTE: Final = "/api/history/facets"  # Run status facet JSON API path
WEB_API_RUN_DETAIL_ROUTE: Final = "/api/history/{run_id}"  # Run detail JSON API path
WEB_API_UNDO_PLAN_ROUTE: Final = "/api/history/{run_id}/undo-plan"  # durable Undo Plan operation JSON API path
WEB_API_RUN_EVENTS_ROUTE: Final = "/api/history/{run_id}/events"  # FileEvent browse JSON API path
WEB_API_RUN_EVENT_FACETS_ROUTE: Final = "/api/history/{run_id}/events/facets"  # FileEvent facet JSON API path
WEB_API_RUN_EVENT_GROUPS_ROUTE: Final = "/api/history/{run_id}/events/groups"  # FileEvent group JSON API path
WEB_STATIC_EXPORT_DIRECTORY_NAME: Final = "static_dist"  # package directory for built Web UI assets
WEB_STATIC_ASSET_ROUTE: Final = "/assets"  # Vite content-hashed asset route prefix
WEB_STATIC_EXPORT_INDEX_FILE_NAME: Final = "index.html"  # Web UI entry document
WEB_STATIC_EXPORT_MISSING_MESSAGE: Final = "Web UI build is unavailable."  # missing Web UI build response text
WEB_STATIC_ASSET_NOT_FOUND_MESSAGE: Final = "Web UI static asset was not found."  # missing static asset text
WEB_API_NOT_FOUND_MESSAGE: Final = "Web API endpoint was not found."  # unknown API endpoint response text
WEB_METHOD_NOT_ALLOWED_MESSAGE: Final = "Method is not allowed for this endpoint."  # unsupported HTTP method text
WEB_UI_NOT_FOUND_MESSAGE: Final = "Web UI route was not found."  # rejected UI fallback response text
WEB_URL_SCHEME: Final = "http"  # scheme used for the local Web UI browser URL
MILLISECONDS_PER_SECOND: Final = 1000  # conversion factor from seconds to milliseconds
WEB_PRODUCTION_ALLOWED_HOSTS: Final = ("127.0.0.1", "localhost")  # accepted production Host header values
WEB_HTML_ACCEPT_MEDIA_TYPE: Final = "text/html"  # media type required for SPA fallback
WEB_INDEX_CACHE_CONTROL: Final = "no-cache"  # cache policy for index and HTML fallback responses
WEB_ASSET_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"  # cache policy for hashed Vite assets
WEB_CONTENT_SECURITY_POLICY: Final = (
    "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)  # local-only Web content security policy
WEB_REFERRER_POLICY: Final = "no-referrer"  # Web response referrer policy
WEB_ASSET_HASH_MIN_LENGTH: Final = 8  # minimum Vite content hash length in packaged asset names, characters
HTTP_BAD_REQUEST_STATUS: Final = 400  # malformed HTTP request status code
HTTP_ACCEPTED_STATUS: Final = 202  # durable Operation accepted status code
HTTP_FORBIDDEN_STATUS: Final = 403  # rejected state-changing request authorization status code
HTTP_CONFLICT_STATUS: Final = 409  # state or idempotency conflict status code
HTTP_GONE_STATUS: Final = 410  # retained Operation result expired status code
HTTP_OK_STATUS: Final = 200  # successful HTTP request status code
HTTP_NOT_FOUND_STATUS: Final = 404  # missing HTTP resource status code
HTTP_METHOD_NOT_ALLOWED_STATUS: Final = 405  # unsupported HTTP method status code
HTTP_UNPROCESSABLE_CONTENT_STATUS: Final = 422  # structurally invalid request status code
HTTP_INTERNAL_ERROR_STATUS: Final = 500  # unexpected server failure status code
HTTP_SERVICE_UNAVAILABLE_STATUS: Final = 503  # missing packaged Web build status code
WEB_CORRELATION_HEADER_NAME: Final = "X-OMYM2-Correlation-ID"  # request correlation response header
WEB_CSP_HEADER_NAME: Final = "Content-Security-Policy"  # content security policy response header
WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME: Final = "X-Content-Type-Options"  # MIME sniffing response header
WEB_CONTENT_TYPE_OPTIONS_VALUE: Final = "nosniff"  # MIME sniffing prohibition response value
WEB_REFERRER_POLICY_HEADER_NAME: Final = "Referrer-Policy"  # referrer policy response header
OPERATION_POLL_INITIAL_SECONDS: Final = 0.5  # initial Operation polling delay, seconds, > 0
OPERATION_POLL_BACKOFF_FACTOR: Final = 2.0  # unchanged Operation polling multiplier, >= 1
OPERATION_POLL_MAX_SECONDS: Final = 5.0  # maximum Operation polling delay, seconds, >= initial
OPERATION_RECONCILE_INTERVAL_SECONDS: Final = 5.0  # Web reconciliation supervisor interval, seconds, > 0
OPERATION_RESULT_RETENTION_HOURS: Final = 24  # full terminal Operation retention, hours, >= 1
OPERATION_TOMBSTONE_RETENTION_DAYS: Final = 30  # Operation idempotency tombstone retention, days, >= 1
OPERATION_REQUEST_FINGERPRINT_ALGORITHM: Final = "sha256"  # canonical Operation request digest algorithm
OPERATION_WORKER_COUNT: Final = 1  # exclusive background Operation worker slots, exactly 1
LOGICAL_PATH_SEPARATOR: Final = "/"
PARENT_DIRECTORY_REFERENCE: Final = ".."
PLAN_ACTION_SORT_ORDER_START: Final = 1  # first review-order value stored for PlanActions
PLAN_ACTION_SORT_ORDER_STEP: Final = 1  # increment between adjacent PlanAction sort orders
FILE_EVENT_SEQUENCE_START: Final = 1  # first durable mutation event sequence number in a Run
FILE_EVENT_SEQUENCE_STEP: Final = 1  # increment between adjacent durable mutation events

ALLOWED_COMMAND_MODES: Final = frozenset({"plan_first"})  # supported command default_mode values
ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES: Final = frozenset({"skip"})  # duplicate content decisions
ALLOWED_COLLISION_MISSING_METADATA_POLICIES: Final = frozenset({"block"})  # missing metadata decisions
ALLOWED_COLLISION_TARGET_EXISTS_POLICIES: Final = frozenset({"conflict"})  # target collision decisions
ALBUM_YEAR_RESOLUTION_LATEST: Final = "latest"  # choose the newest usable year in an album group
ALBUM_YEAR_RESOLUTION_OLDEST: Final = "oldest"  # choose the oldest usable year in an album group
ALBUM_YEAR_RESOLUTION_MOST_FREQUENT: Final = "most_frequent"  # choose the modal album-group year
ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS: Final = frozenset(
    {
        ALBUM_YEAR_RESOLUTION_LATEST,
        ALBUM_YEAR_RESOLUTION_OLDEST,
        ALBUM_YEAR_RESOLUTION_MOST_FREQUENT,
    }
)  # supported album-year resolution method values
PATH_POLICY_DISC_NUMBER_STYLE_PLAIN: Final = "plain"  # render {disc} as the numeric tag value
PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED: Final = "d_prefixed"  # render {disc} as D plus the numeric tag value
PATH_POLICY_DISC_NUMBER_CONDITION_ALWAYS: Final = "always"  # render {disc} regardless of inferred album disc count
PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS: Final = (
    "multiple_discs"  # render {disc} only when album context is multi-disc
)
ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES: Final = frozenset(
    {PATH_POLICY_DISC_NUMBER_STYLE_PLAIN, PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED}
)  # supported {disc} display style values
ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS: Final = frozenset(
    {PATH_POLICY_DISC_NUMBER_CONDITION_ALWAYS, PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS}
)  # supported {disc} rendering condition values
CONFIG_VERSION: Final = 2  # supported clean-slate user config schema version
DEFAULT_COMMAND_MODE: Final = "plan_first"  # initial plan creation mode for mutating commands
DEFAULT_ADD_AUTO_APPLY: Final = False  # add command auto-apply default
DEFAULT_ORGANIZE_AUTO_APPLY: Final = False  # organize command auto-apply default
DEFAULT_REFRESH_AUTO_APPLY: Final = False  # refresh command auto-apply default
DEFAULT_ALBUM_YEAR_RESOLUTION: Final = ALBUM_YEAR_RESOLUTION_LATEST  # album-group year resolution default
DEFAULT_PATH_POLICY_TEMPLATE: Final = (
    "{album_artist}/{year}_{album}/{disc}-{track}_{title}"  # canonical path stem template
)
DEFAULT_UNKNOWN_ARTIST: Final = "Unknown Artist"  # fallback artist text for path generation
DEFAULT_UNKNOWN_ALBUM: Final = "Unknown Album"  # fallback album text for path generation
DEFAULT_PATH_POLICY_SANITIZE: Final = True  # sanitize metadata text before it becomes path text
DEFAULT_MAX_FILENAME_LENGTH: Final = 180  # maximum generated path component length, characters
DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE: Final = PATH_POLICY_DISC_NUMBER_STYLE_PLAIN  # default {disc} display style
DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION: Final = PATH_POLICY_DISC_NUMBER_CONDITION_ALWAYS  # default {disc} condition
DEFAULT_METADATA_PREFER_ALBUM_ARTIST: Final = True  # prefer album artist when metadata provides it
DEFAULT_METADATA_REQUIRE_TITLE: Final = True  # require title metadata during plan creation
DEFAULT_METADATA_REQUIRE_ARTIST: Final = True  # require artist metadata during plan creation
DEFAULT_METADATA_REQUIRE_ALBUM: Final = False  # require album metadata during plan creation
DEFAULT_COLLISION_ON_TARGET_EXISTS: Final = "conflict"  # target collision policy name
DEFAULT_COLLISION_ON_DUPLICATE_HASH: Final = "skip"  # duplicate content policy name
DEFAULT_COLLISION_ON_MISSING_METADATA: Final = "block"  # missing metadata policy name
DEFAULT_ARTIST_ID_MAX_LENGTH: Final = 8  # maximum generated artist ID length, characters
DEFAULT_ARTIST_ID_FALLBACK: Final = "NOART"  # artist ID used when source text has no usable characters
MUSICBRAINZ_CACHE_POLICY_STICKY_POSITIVE: Final = "sticky_positive"  # persist accepted positive provider results
ALLOWED_MUSICBRAINZ_CACHE_POLICIES: Final = frozenset(
    {MUSICBRAINZ_CACHE_POLICY_STICKY_POSITIVE}
)  # supported provider-result cache policies
DEFAULT_MUSICBRAINZ_ENABLED: Final = False  # opt-in automatic MusicBrainz lookup default
DEFAULT_MUSICBRAINZ_APPLICATION_NAME: Final = "OMYM2"  # application identity sent to MusicBrainz
DEFAULT_MUSICBRAINZ_CONTACT: Final = "https://github.com/muray0196/omym2"  # MusicBrainz contact identity
DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS: Final = 5.0  # MusicBrainz request timeout, seconds, > 0
DEFAULT_MUSICBRAINZ_RETRY_LIMIT: Final = 1  # retries after the initial MusicBrainz request, attempts, >= 0
DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS: Final = 1.0  # delay between MusicBrainz requests, seconds, >= 1
DEFAULT_MUSICBRAINZ_CACHE_POLICY: Final = (
    MUSICBRAINZ_CACHE_POLICY_STICKY_POSITIVE  # accepted positive provider-result cache behavior
)
DEFAULT_FASTTEXT_MODEL_PATH: Final[str | None] = None  # optional fastText model path
DEFAULT_FASTTEXT_MINIMUM_CONFIDENCE: Final = 0.8  # minimum accepted fastText confidence, 0..1
FASTTEXT_MINIMUM_CONFIDENCE_MIN: Final = 0.0  # lowest accepted fastText confidence
FASTTEXT_MINIMUM_CONFIDENCE_MAX: Final = 1.0  # highest accepted fastText confidence
DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES: Final = 1_048_576  # file hash read chunk size, bytes, >= 1
LOGGING_LEVEL_DEBUG: Final = "DEBUG"  # diagnostic logging level
LOGGING_LEVEL_INFO: Final = "INFO"  # informational logging level
LOGGING_LEVEL_WARNING: Final = "WARNING"  # warning logging level
LOGGING_LEVEL_ERROR: Final = "ERROR"  # error logging level
LOGGING_LEVEL_CRITICAL: Final = "CRITICAL"  # critical logging level
ALLOWED_LOGGING_LEVELS: Final = frozenset(
    {
        LOGGING_LEVEL_DEBUG,
        LOGGING_LEVEL_INFO,
        LOGGING_LEVEL_WARNING,
        LOGGING_LEVEL_ERROR,
        LOGGING_LEVEL_CRITICAL,
    }
)  # supported persisted logging levels
DEFAULT_LOGGING_DESTINATION: Final[str | None] = None  # application-data default log destination
DEFAULT_LOGGING_LEVEL: Final = DESKTOP_LOG_LEVEL  # persisted logging level default
DEFAULT_LOGGING_ROTATION_MAX_BYTES: Final = DESKTOP_LOG_MAX_BYTES  # log rotation threshold, bytes, >= 1
DEFAULT_LOGGING_RETENTION_FILES: Final = DESKTOP_LOG_BACKUP_COUNT  # retained rotated log files, files, >= 1
DEFAULT_COMPANIONS_ENABLED: Final = False  # opt-in companion lyrics and artwork processing default
DEFAULT_UNPROCESSED_ENABLED: Final = False  # opt-in unprocessed-file collection default
DEFAULT_UNPROCESSED_DIRECTORY: Final = "Unprocessed"  # unprocessed destination directory component
UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN: Final = 1  # minimum reviewed unprocessed result count, files
UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX: Final = 500  # maximum reviewed unprocessed result count, files
DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT: Final = 100  # default reviewed unprocessed result count, files
PORTABLE_PATH_CONTROL_CHARACTER_LIMIT: Final = 32  # first non-control Unicode code point allowed in path components
PORTABLE_PATH_FORBIDDEN_CHARACTERS: Final = frozenset('<>:"/\\|?*')  # Windows-invalid path component chars
ARTIST_ID_ALLOWED_PATTERN: Final = r"[A-Za-z0-9]+"  # characters kept while normalizing artist ID input
ARTIST_ID_ENTRY_VALUE_PATTERN: Final = (
    r"^[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*$"  # saved artist ID entry values accepted as sanitizer-stable
)
ARTIST_ID_SPLIT_PATTERN: Final = r"[\s-]+"  # separators that divide artist names into allocation words
ARTIST_ID_MULTI_ARTIST_SEPARATOR: Final = ","  # separator between source artist names in metadata text
ARTIST_ID_VOWELS: Final = frozenset("AEIOU")  # vowels deprioritized after the first character in a word
FASTTEXT_JAPANESE_LABEL: Final = "__label__ja"  # fastText label that means Japanese text
ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN: Final = (
    DEFAULT_FASTTEXT_MINIMUM_CONFIDENCE  # minimum fastText confidence for automatic naming, 0..1
)
ARTIST_NAME_LANGUAGE_CONFIDENCE_MAX: Final = FASTTEXT_MINIMUM_CONFIDENCE_MAX  # maximum valid fastText confidence
ARTIST_NAME_COMPOSITE_SEPARATOR: Final = ","  # unsupported multi-artist separator during initial resolution
MUSICBRAINZ_API_BASE_URL: Final = "https://musicbrainz.org/ws/2"  # MusicBrainz web service base URL
MUSICBRAINZ_ARTIST_SEARCH_LIMIT: Final = 5  # artist search result cap per lookup
MUSICBRAINZ_ARTIST_MATCH_SCORE_MIN: Final = 95  # minimum accepted artist search score, 0..100
MUSICBRAINZ_ARTIST_AMBIGUITY_MARGIN: Final = 5  # inclusive score gap that keeps distinct identities ambiguous
MUSICBRAINZ_RATE_LIMIT_SECONDS: Final = DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS  # minimum delay between requests
MUSICBRAINZ_TIMEOUT_SECONDS: Final = DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS  # MusicBrainz HTTP timeout, seconds
MUSICBRAINZ_USER_AGENT: Final = "OMYM2/0.1 (https://github.com/muray0196/omym2)"  # MusicBrainz client UA
CONTENT_FINGERPRINT_ALGORITHM: Final = "sha256"  # content fingerprint hash algorithm
CONTENT_HASH_READ_CHUNK_SIZE_BYTES: Final = DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES  # hash read chunk size, bytes
FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT: Final = 1  # minimum parallel snapshot captures, workers, >= 1
FILE_SNAPSHOT_CAPTURE_WORKER_COUNT: Final = 8  # maximum parallel snapshot captures, workers, >= 1
CONFIG_FINGERPRINT_ALGORITHM: Final = "sha256"  # config fingerprint hash algorithm
CONFIG_FINGERPRINT_ENCODING: Final = "utf-8"  # config fingerprint payload encoding
CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR: Final = ","  # canonical JSON item separator
CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR: Final = ":"  # canonical JSON key separator
CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY: Final = (
    "path_policy_behavior_version"  # canonical JSON key for path policy behavior identity
)
CONFIG_FINGERPRINT_PATH_POLICY_CONFIG_KEY: Final = "path_policy"  # canonical JSON key for path policy settings
METADATA_FINGERPRINT_ALGORITHM: Final = "sha256"  # metadata fingerprint hash algorithm
METADATA_FINGERPRINT_ENCODING: Final = "utf-8"  # metadata fingerprint payload encoding
METADATA_FINGERPRINT_JSON_ITEM_SEPARATOR: Final = ","  # canonical JSON item separator
METADATA_FINGERPRINT_JSON_KEY_SEPARATOR: Final = ":"  # canonical JSON key separator
PERSISTED_JSON_ITEM_SEPARATOR: Final = ","  # compact JSON item separator for SQLite payloads
PERSISTED_JSON_KEY_SEPARATOR: Final = ":"  # compact JSON key separator for SQLite payloads
PATH_EXTENSION_PREFIX: Final = "."  # separator before generated file extensions
SANITIZER_ALLOWED_EXTENSION_PATTERN: Final = r"^[A-Za-z0-9]+$"  # extension pattern preserved by sanitizer
SANITIZER_FALLBACK_TITLE: Final = "Unknown-Title"  # title text used when sanitized title is empty
SANITIZER_HYPHEN_RUN_PATTERN: Final = r"-+"  # repeated hyphens collapsed after replacement
SANITIZER_REPLACEMENT: Final = "-"  # replacement for sanitizer characters outside [\w-]
SANITIZER_UNSAFE_PATTERN: Final = r"[^\w-]"  # characters converted to sanitizer replacement
SANITIZER_UTF8_ENCODING: Final = "utf-8"  # encoding used for sanitizer byte limits
PATH_POLICY_ALBUM_ARTIST_PLACEHOLDER: Final = "album_artist"  # template field using album-artist display naming
PATH_POLICY_ARTIST_PLACEHOLDER: Final = "artist"  # template field using track-artist display naming
PATH_POLICY_DISC_NUMBER_PLACEHOLDER: Final = "disc"  # template field controlled by disc rendering settings
PATH_POLICY_ARTIST_ID_PLACEHOLDER: Final = "artist_id"  # template field resolved from editable artist ID config
PATH_POLICY_YEAR_PLACEHOLDER: Final = "year"  # template field resolved from album-year metadata
PATH_POLICY_ALLOWED_PLACEHOLDERS: Final[tuple[str, ...]] = (
    PATH_POLICY_ALBUM_ARTIST_PLACEHOLDER,
    "album",
    PATH_POLICY_DISC_NUMBER_PLACEHOLDER,
    "track",
    "title",
    PATH_POLICY_ARTIST_PLACEHOLDER,
    PATH_POLICY_YEAR_PLACEHOLDER,
    PATH_POLICY_ARTIST_ID_PLACEHOLDER,
)  # placeholders allowed in path policy stem templates
PATH_POLICY_BEHAVIOR_VERSION: Final = 7  # version included in hashes when canonical path behavior changes
PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT: Final = "_"  # replacement for empty generated path components
PATH_POLICY_DISC_NUMBER_PREFIX: Final = "D"  # prefix used by d_prefixed {disc} rendering
PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{digit}" for digit in range(1, 10)} | {f"LPT{digit}" for digit in range(1, 10)}
)  # Windows reserved device names treated as sanitized-to-empty stems, case-insensitive
PATH_POLICY_TRACK_NUMBER_WIDTH: Final = 2  # zero-padding width for generated track numbers
PATH_POLICY_PREVIEW_TITLE: Final = "Example Song"  # sample title shown in settings preview
PATH_POLICY_PREVIEW_ARTIST: Final = "Aimer"  # sample artist shown in settings preview
PATH_POLICY_PREVIEW_ALBUM: Final = "Example Album"  # sample album shown in settings preview
PATH_POLICY_PREVIEW_ALBUM_ARTIST: Final = "Aimer"  # sample album artist shown in settings preview
PATH_POLICY_PREVIEW_YEAR: Final = 2024  # sample release year shown in settings preview
PATH_POLICY_PREVIEW_DISC_NUMBER: Final = 1  # sample disc number shown in settings preview
PATH_POLICY_PREVIEW_DISC_TOTAL: Final = 2  # sample disc total shown in settings preview
PATH_POLICY_PREVIEW_TRACK_NUMBER: Final = 3  # sample track number shown in settings preview
PATH_POLICY_PREVIEW_FILE_EXTENSION: Final = ".FLAC"  # sample source suffix shown in settings preview
SQLITE_CONNECTION_TIMEOUT_SECONDS: Final = 30.0  # SQLite connection busy timeout, seconds
SQLITE_MIGRATION_FILE_ENCODING: Final = "utf-8"  # SQLite migration resource encoding
SQLITE_MIGRATION_FILE_EXTENSION: Final = ".sql"  # migration resource file extension
SQLITE_SYNCHRONOUS_PRAGMA: Final = "PRAGMA synchronous = FULL"  # per-commit WAL durability pragma
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
