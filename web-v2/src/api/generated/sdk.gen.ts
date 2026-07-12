/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

import type { Client, ClientMeta, Options as Options2, RequestResult, TDataShape } from './client';
import { client } from './client.gen';
import type { GetBootstrapData, GetBootstrapErrors, GetBootstrapResponses } from './types.gen';

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
