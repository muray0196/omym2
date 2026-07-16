"""
Summary: Implements read-only Track inspection Web API routes.
Why: Gives the renewed Library UI persisted list, detail, facet, and group data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003  # FastAPI resolves UUID route annotations at registration.

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse  # noqa: TC002  # FastAPI resolves response annotations at registration.

from omym2.adapters.web.routes.api_context import (
    ApiContext,  # FastAPI resolves dependency annotations at registration.
    TracksRouteContext,
)
from omym2.adapters.web.routes.api_responses import api_failure_response
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiErrorCode
from omym2.adapters.web.schemas.browsing import FacetValueResource, GroupResource, PageInfo, PaginatedData
from omym2.adapters.web.schemas.tracks import (
    TrackFacetsData,
    TrackFacetSets,
    TrackGroupsData,
    TrackMetadataResource,
    TrackResource,
)
from omym2.config import (
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_TRACK_DETAIL_ROUTE,
    WEB_API_TRACK_FACETS_ROUTE,
    WEB_API_TRACK_GROUPS_ROUTE,
    WEB_API_TRACKS_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
)
from omym2.domain.models.track import (
    TrackGrouping,
    TrackStatus,
)
from omym2.features.tracks.dto import (
    GetTrackRequest,
    GroupTracksRequest,
    ListTracksRequest,
    TrackStatusFacetsRequest,
)
from omym2.features.tracks.usecases.get_track import TrackNotFoundError
from omym2.shared.ids import LibraryId, TrackId
from omym2.shared.pagination import (
    DEFAULT_PAGE_LIMIT,
    CursorDecodeError,
    PageRequest,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)

if TYPE_CHECKING:
    from omym2.domain.models.track import Track
    from omym2.shared.pagination import Page

TRACK_NOT_FOUND_MESSAGE = "Track was not found."
INVALID_TRACK_QUERY_MESSAGE = "Track browse query is invalid."
TRACK_HANDLERS_UNAVAILABLE_MESSAGE = "Track route handlers are unavailable."
CORRELATION_HEADER_SCHEMA = {
    "description": "Request correlation identifier written to server logs.",
    "schema": {"type": "string"},
}


def get_track_route_handlers(context: ApiContext) -> TracksRouteContext:
    """Resolve the Track-specific collaborators from the shared route context."""
    handlers = context.tracks
    if handlers is None:
        raise RuntimeError(TRACK_HANDLERS_UNAVAILABLE_MESSAGE)
    return handlers


type TracksContext = Annotated[TracksRouteContext, Depends(get_track_route_handlers)]


def create_tracks_router() -> APIRouter:
    """Create the read-only Track list, detail, facet, and group routes."""
    router = APIRouter()
    response_headers = {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}
    error_responses = {
        HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
        HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
        HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
    }

    @router.get(
        WEB_API_TRACKS_ROUTE,
        operation_id="listTracks",
        response_model=ApiEnvelope[PaginatedData[TrackResource]],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def list_tracks(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: TracksContext,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: TrackStatus | None = None,
        track_id: UUID | None = None,
        library_id: UUID | None = None,
        group_by: TrackGrouping | None = None,
        group_key: str | None = None,
        limit: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> ApiEnvelope[PaginatedData[TrackResource]] | JSONResponse:
        try:
            page_request = _page_request(limit, cursor)
            page = context.list_tracks(
                ListTracksRequest(
                    library_id=None if library_id is None else LibraryId(library_id),
                    track_id=None if track_id is None else TrackId(track_id),
                    search=query_text,
                    status=status,
                    grouping=group_by,
                    group_key=group_key,
                    page=page_request,
                )
            )
        except CursorDecodeError, ValueError:
            return _invalid_track_query("query.cursor" if cursor is not None else "query.group_by")
        items = tuple(_track_resource(track) for track in page.items)
        return ApiEnvelope(data=PaginatedData(items=items, page=_page_info(page, page_request)), errors=())

    @router.get(
        WEB_API_TRACK_FACETS_ROUTE,
        operation_id="getTrackFacets",
        response_model=ApiEnvelope[TrackFacetsData],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_track_facets(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: TracksContext,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        library_id: UUID | None = None,
    ) -> ApiEnvelope[TrackFacetsData]:
        result = context.get_track_status_facets(
            TrackStatusFacetsRequest(
                library_id=None if library_id is None else LibraryId(library_id),
                search=query_text,
            )
        )
        return ApiEnvelope(
            data=TrackFacetsData(
                facets=TrackFacetSets(
                    status=tuple(
                        FacetValueResource(value=TrackStatus(facet.value), count=facet.count) for facet in result.facets
                    )
                ),
                total=result.total,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_TRACK_GROUPS_ROUTE,
        operation_id="getTrackGroups",
        response_model=ApiEnvelope[TrackGroupsData],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_track_groups(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: TracksContext,
        group_by: TrackGrouping,
        parent_key: str | None = None,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: TrackStatus | None = None,
        library_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> ApiEnvelope[TrackGroupsData] | JSONResponse:
        try:
            page_request = _page_request(limit, cursor)
            page = context.group_tracks(
                GroupTracksRequest(
                    grouping=group_by,
                    library_id=None if library_id is None else LibraryId(library_id),
                    parent_key=parent_key,
                    search=query_text,
                    status=status,
                    page=page_request,
                )
            )
        except CursorDecodeError, ValueError:
            return _invalid_track_query("query.cursor" if cursor is not None else "query.parent_key")

        return ApiEnvelope(
            data=TrackGroupsData(
                group_by=group_by,
                items=tuple(GroupResource(key=group.key, label=group.label, count=group.count) for group in page.items),
                page=_page_info(page, page_request),
            ),
            errors=(),
        )

    @router.get(
        WEB_API_TRACK_DETAIL_ROUTE,
        operation_id="getTrack",
        response_model=ApiEnvelope[TrackResource],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_track(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        track_id: UUID,
        context: TracksContext,
    ) -> ApiEnvelope[TrackResource] | JSONResponse:
        try:
            track = context.get_track(GetTrackRequest(TrackId(track_id)))
        except TrackNotFoundError:
            return api_failure_response(
                HTTP_NOT_FOUND_STATUS,
                ApiErrorCode.TRACK_NOT_FOUND,
                TRACK_NOT_FOUND_MESSAGE,
                field="path.track_id",
            )
        return ApiEnvelope(data=_track_resource(track), errors=())

    return router


def _page_request(limit: int, cursor: str | None) -> PageRequest:
    return PageRequest(
        limit=clamp_limit(limit),
        cursor_key=None if cursor is None else decode_cursor(cursor),
    )


def _page_info[Item](page: Page[Item], request: PageRequest) -> PageInfo:
    next_cursor = None if page.next_cursor_key is None else encode_cursor(page.next_cursor_key)
    return PageInfo(limit=request.limit, next_cursor=next_cursor, total=page.total)


def _track_resource(track: Track) -> TrackResource:
    metadata = track.metadata
    return TrackResource(
        track_id=track.track_id,
        library_id=track.library_id,
        current_path=track.current_path,
        canonical_path=track.canonical_path,
        content_hash=track.content_hash,
        metadata_hash=track.metadata_hash,
        size=track.size,
        mtime=track.mtime,
        metadata=TrackMetadataResource(
            title=metadata.title,
            artist=metadata.artist,
            album=metadata.album,
            album_artist=metadata.album_artist,
            genre=metadata.genre,
            year=metadata.year,
            track_number=metadata.track_number,
            track_total=metadata.track_total,
            disc_number=metadata.disc_number,
            disc_total=metadata.disc_total,
        ),
        status=track.status,
        first_seen_at=track.first_seen_at,
        last_seen_at=track.last_seen_at,
        updated_at=track.updated_at,
    )


def _invalid_track_query(field: str) -> JSONResponse:
    return api_failure_response(
        HTTP_UNPROCESSABLE_CONTENT_STATUS,
        ApiErrorCode.VALIDATION_FAILED,
        INVALID_TRACK_QUERY_MESSAGE,
        field=field,
    )
