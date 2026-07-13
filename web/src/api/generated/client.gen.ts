/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

import { type Client, type ClientOptions, type Config, createClient, createConfig } from './client';
import type { ClientOptions as ClientOptions2 } from './types.gen';

/**
 * The `createClientConfig()` function will be called on client initialization
 * and the returned object will become the client's initial configuration.
 *
 * You may want to initialize your client this way instead of calling
 * `setConfig()`. This is useful for example if you're using Next.js
 * to ensure your client always has the correct values.
 */
export type CreateClientConfig<T extends ClientOptions = ClientOptions2> = (override?: Config<ClientOptions & T>) => Config<Required<ClientOptions> & T>;

export const client: Client = createClient(createConfig<ClientOptions2>());
