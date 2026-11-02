# @worlds/client

TypeScript client for the Worlds data-plane API at `worlds-api.wazoo.dev`.

This package is generated from the canonical Worlds API OpenAPI document
(committed in `openapi/openapi.json`). Use it for data-plane operations against
a hosted or self-hosted Worlds service: world search, SPARQL, import, export,
reindex, world lifecycle, and data-plane API keys.

For the embeddable SDK (in-process graph operations over any backend), use
`@worlds/sdk`. For platform management-plane operations (users, usage, limits,
billing) use `@wazoo/client`.

## Install

```sh
npx jsr add @worlds/client
```

## Usage

```ts
import { createClient, searchWorld } from "@worlds/client";

const client = createClient({
  baseUrl: "https://worlds-api.wazoo.dev",
  auth: process.env.WORLDS_DATA_PLANE_TOKEN,
});

const response = await searchWorld({
  client,
  path: { id: "w_<world-uid>" },
  body: { query: "explores" },
});

console.log(response.data?.results);
```

## Development

Requires Deno (version pinned in `.tool-versions`).

```sh
deno task ci
```

Run `deno task sync:openapi` to refresh `openapi/openapi.json`. By default it
reads the checked-in snapshot at `../worlds-api/openapi/openapi.json` (a sibling
checkout of the Worlds API repo). Set
`WORLDS_API_OPENAPI_URL=https://worlds-api.wazoo.dev/openapi.json` to sync from
a deployed API. CI runs `deno task openapi:check` so spec drift fails the build.

Run `deno task generate` to regenerate `src/generated/` from the synced spec via
`@hey-api/openapi-ts`.
