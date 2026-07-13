/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

import type { Client, ClientMeta, Options as Options2, RequestResult, TDataShape } from './client';
import { client } from './client.gen';
import type { GetBootstrapData, GetBootstrapErrors, GetBootstrapResponses, GetCheckIssueFacetsData, GetCheckIssueFacetsErrors, GetCheckIssueFacetsResponses, GetCheckIssueGroupsData, GetCheckIssueGroupsErrors, GetCheckIssueGroupsResponses, GetCheckIssuesData, GetCheckIssuesErrors, GetCheckIssuesResponses, GetHistoryData, GetHistoryErrors, GetHistoryFacetsData, GetHistoryFacetsErrors, GetHistoryFacetsResponses, GetHistoryResponses, GetLibrariesData, GetLibrariesErrors, GetLibrariesResponses, GetLibraryData, GetLibraryErrors, GetLibraryResponses, GetPlanActionFacetsData, GetPlanActionFacetsErrors, GetPlanActionFacetsResponses, GetPlanData, GetPlanErrors, GetPlanResponses, GetRunData, GetRunErrors, GetRunEventFacetsData, GetRunEventFacetsErrors, GetRunEventFacetsResponses, GetRunEventGroupsData, GetRunEventGroupsErrors, GetRunEventGroupsResponses, GetRunEventsData, GetRunEventsErrors, GetRunEventsResponses, GetRunResponses, GetTrackData, GetTrackErrors, GetTrackFacetsData, GetTrackFacetsErrors, GetTrackFacetsResponses, GetTrackGroupsData, GetTrackGroupsErrors, GetTrackGroupsResponses, GetTrackResponses, GroupPlanActionsData, GroupPlanActionsErrors, GroupPlanActionsResponses, ListPlanActionsData, ListPlanActionsErrors, ListPlanActionsResponses, ListPlansData, ListPlansErrors, ListPlansResponses, ListTracksData, ListTracksErrors, ListTracksResponses } from './types.gen';

export type Options<TData extends TDataShape = TDataShape, ThrowOnError extends boolean = boolean, TResponse = unknown> = Options2<TData, ThrowOnError, TResponse> & {
    /**
     * You can provide a client instance returned by `createClient()` instead of
     * individual options. This might be also useful if you want to implement a
     * custom client.
     */
    client?: Client;
    /**
     * You can pass arbitrary values through the `meta` object. This can be
     * used to access values that aren't defined as part of the SDK function.
     */
    meta?: keyof ClientMeta extends never ? Record<string, unknown> : ClientMeta;
};

/**
 * Get Bootstrap
 */
export const getBootstrap = <ThrowOnError extends boolean = false>(options?: Options<GetBootstrapData, ThrowOnError>): RequestResult<GetBootstrapResponses, GetBootstrapErrors, ThrowOnError> => (options?.client ?? client).get<GetBootstrapResponses, GetBootstrapErrors, ThrowOnError>({ url: '/api/bootstrap', ...options });

/**
 * Get Check Issues
 */
export const getCheckIssues = <ThrowOnError extends boolean = false>(options?: Options<GetCheckIssuesData, ThrowOnError>): RequestResult<GetCheckIssuesResponses, GetCheckIssuesErrors, ThrowOnError> => (options?.client ?? client).get<GetCheckIssuesResponses, GetCheckIssuesErrors, ThrowOnError>({ url: '/api/check', ...options });

/**
 * Get Check Issue Facets
 */
export const getCheckIssueFacets = <ThrowOnError extends boolean = false>(options?: Options<GetCheckIssueFacetsData, ThrowOnError>): RequestResult<GetCheckIssueFacetsResponses, GetCheckIssueFacetsErrors, ThrowOnError> => (options?.client ?? client).get<GetCheckIssueFacetsResponses, GetCheckIssueFacetsErrors, ThrowOnError>({ url: '/api/check/facets', ...options });

/**
 * Get Check Issue Groups
 */
export const getCheckIssueGroups = <ThrowOnError extends boolean = false>(options: Options<GetCheckIssueGroupsData, ThrowOnError>): RequestResult<GetCheckIssueGroupsResponses, GetCheckIssueGroupsErrors, ThrowOnError> => (options.client ?? client).get<GetCheckIssueGroupsResponses, GetCheckIssueGroupsErrors, ThrowOnError>({ url: '/api/check/groups', ...options });

/**
 * Get History
 */
export const getHistory = <ThrowOnError extends boolean = false>(options?: Options<GetHistoryData, ThrowOnError>): RequestResult<GetHistoryResponses, GetHistoryErrors, ThrowOnError> => (options?.client ?? client).get<GetHistoryResponses, GetHistoryErrors, ThrowOnError>({ url: '/api/history', ...options });

/**
 * Get History Facets
 */
export const getHistoryFacets = <ThrowOnError extends boolean = false>(options?: Options<GetHistoryFacetsData, ThrowOnError>): RequestResult<GetHistoryFacetsResponses, GetHistoryFacetsErrors, ThrowOnError> => (options?.client ?? client).get<GetHistoryFacetsResponses, GetHistoryFacetsErrors, ThrowOnError>({ url: '/api/history/facets', ...options });

/**
 * Get Run
 */
export const getRun = <ThrowOnError extends boolean = false>(options: Options<GetRunData, ThrowOnError>): RequestResult<GetRunResponses, GetRunErrors, ThrowOnError> => (options.client ?? client).get<GetRunResponses, GetRunErrors, ThrowOnError>({ url: '/api/history/{run_id}', ...options });

/**
 * Get Run Events
 */
export const getRunEvents = <ThrowOnError extends boolean = false>(options: Options<GetRunEventsData, ThrowOnError>): RequestResult<GetRunEventsResponses, GetRunEventsErrors, ThrowOnError> => (options.client ?? client).get<GetRunEventsResponses, GetRunEventsErrors, ThrowOnError>({ url: '/api/history/{run_id}/events', ...options });

/**
 * Get Run Event Facets
 */
export const getRunEventFacets = <ThrowOnError extends boolean = false>(options: Options<GetRunEventFacetsData, ThrowOnError>): RequestResult<GetRunEventFacetsResponses, GetRunEventFacetsErrors, ThrowOnError> => (options.client ?? client).get<GetRunEventFacetsResponses, GetRunEventFacetsErrors, ThrowOnError>({ url: '/api/history/{run_id}/events/facets', ...options });

/**
 * Get Run Event Groups
 */
export const getRunEventGroups = <ThrowOnError extends boolean = false>(options: Options<GetRunEventGroupsData, ThrowOnError>): RequestResult<GetRunEventGroupsResponses, GetRunEventGroupsErrors, ThrowOnError> => (options.client ?? client).get<GetRunEventGroupsResponses, GetRunEventGroupsErrors, ThrowOnError>({ url: '/api/history/{run_id}/events/groups', ...options });

/**
 * Get Libraries
 */
export const getLibraries = <ThrowOnError extends boolean = false>(options?: Options<GetLibrariesData, ThrowOnError>): RequestResult<GetLibrariesResponses, GetLibrariesErrors, ThrowOnError> => (options?.client ?? client).get<GetLibrariesResponses, GetLibrariesErrors, ThrowOnError>({ url: '/api/libraries', ...options });

/**
 * Get Library
 */
export const getLibrary = <ThrowOnError extends boolean = false>(options: Options<GetLibraryData, ThrowOnError>): RequestResult<GetLibraryResponses, GetLibraryErrors, ThrowOnError> => (options.client ?? client).get<GetLibraryResponses, GetLibraryErrors, ThrowOnError>({ url: '/api/libraries/{library_id}', ...options });

/**
 * List Plans
 */
export const listPlans = <ThrowOnError extends boolean = false>(options?: Options<ListPlansData, ThrowOnError>): RequestResult<ListPlansResponses, ListPlansErrors, ThrowOnError> => (options?.client ?? client).get<ListPlansResponses, ListPlansErrors, ThrowOnError>({ url: '/api/plans', ...options });

/**
 * Get Plan
 */
export const getPlan = <ThrowOnError extends boolean = false>(options: Options<GetPlanData, ThrowOnError>): RequestResult<GetPlanResponses, GetPlanErrors, ThrowOnError> => (options.client ?? client).get<GetPlanResponses, GetPlanErrors, ThrowOnError>({ url: '/api/plans/{plan_id}', ...options });

/**
 * List Plan Actions
 */
export const listPlanActions = <ThrowOnError extends boolean = false>(options: Options<ListPlanActionsData, ThrowOnError>): RequestResult<ListPlanActionsResponses, ListPlanActionsErrors, ThrowOnError> => (options.client ?? client).get<ListPlanActionsResponses, ListPlanActionsErrors, ThrowOnError>({ url: '/api/plans/{plan_id}/actions', ...options });

/**
 * Get Plan Action Facets
 */
export const getPlanActionFacets = <ThrowOnError extends boolean = false>(options: Options<GetPlanActionFacetsData, ThrowOnError>): RequestResult<GetPlanActionFacetsResponses, GetPlanActionFacetsErrors, ThrowOnError> => (options.client ?? client).get<GetPlanActionFacetsResponses, GetPlanActionFacetsErrors, ThrowOnError>({ url: '/api/plans/{plan_id}/facets', ...options });

/**
 * Get Plan Action Groups
 */
export const groupPlanActions = <ThrowOnError extends boolean = false>(options: Options<GroupPlanActionsData, ThrowOnError>): RequestResult<GroupPlanActionsResponses, GroupPlanActionsErrors, ThrowOnError> => (options.client ?? client).get<GroupPlanActionsResponses, GroupPlanActionsErrors, ThrowOnError>({ url: '/api/plans/{plan_id}/groups', ...options });

/**
 * List Tracks
 */
export const listTracks = <ThrowOnError extends boolean = false>(options?: Options<ListTracksData, ThrowOnError>): RequestResult<ListTracksResponses, ListTracksErrors, ThrowOnError> => (options?.client ?? client).get<ListTracksResponses, ListTracksErrors, ThrowOnError>({ url: '/api/tracks', ...options });

/**
 * Get Track Facets
 */
export const getTrackFacets = <ThrowOnError extends boolean = false>(options?: Options<GetTrackFacetsData, ThrowOnError>): RequestResult<GetTrackFacetsResponses, GetTrackFacetsErrors, ThrowOnError> => (options?.client ?? client).get<GetTrackFacetsResponses, GetTrackFacetsErrors, ThrowOnError>({ url: '/api/tracks/facets', ...options });

/**
 * Get Track Groups
 */
export const getTrackGroups = <ThrowOnError extends boolean = false>(options: Options<GetTrackGroupsData, ThrowOnError>): RequestResult<GetTrackGroupsResponses, GetTrackGroupsErrors, ThrowOnError> => (options.client ?? client).get<GetTrackGroupsResponses, GetTrackGroupsErrors, ThrowOnError>({ url: '/api/tracks/groups', ...options });

/**
 * Get Track
 */
export const getTrack = <ThrowOnError extends boolean = false>(options: Options<GetTrackData, ThrowOnError>): RequestResult<GetTrackResponses, GetTrackErrors, ThrowOnError> => (options.client ?? client).get<GetTrackResponses, GetTrackErrors, ThrowOnError>({ url: '/api/tracks/{track_id}', ...options });
