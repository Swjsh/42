// Test-only ESM resolve hook (perf/hq-api pass, 2026-09-15).
//
// lib/hq.ts and lib/station.ts (both touched by this pass's perf fix) import
// their sibling module the PRODUCTION way -- `from "./workspace"`, no
// extension -- because the project's own tsconfig (`moduleResolution:
// "bundler"`) has no `allowImportingTsExtensions`, and `next build` type-
// checks every .ts file in the repo (tests included), so an EXTENSIONED
// relative import in a real (non-@ts-nocheck) source file would fail the
// build. Plain `node --test` has no bundler and cannot resolve an
// extensionless specifier on its own (confirmed live: importing lib/hq.ts
// directly throws ERR_MODULE_NOT_FOUND on its own `from "./workspace"`).
//
// This is the reason tests/hq-agents.test.ts's own header gives for why THAT
// module is "import-light by design" -- it has no sibling relative import at
// all, so it never hits this problem. lib/hq.ts and lib/station.ts do have
// one (workspace.ts), so testing their real fs-reader functions (not a copy)
// needs this hook: it only ever retries a bare relative specifier that fails
// to resolve by appending ".ts", and only for THIS test run -- it changes no
// committed source file and has zero effect on `next build` or the running
// server (never referenced by either).
//
// Usage: node --import ./tests/resolve-ts-extensionless.loader.mjs --test tests/hq-perf-cache.test.ts

import { register } from "node:module";

register(new URL("./_resolve-ts-extensionless.hook.mjs", import.meta.url));
