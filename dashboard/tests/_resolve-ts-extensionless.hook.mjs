// The actual resolve hook registered by resolve-ts-extensionless.loader.mjs
// -- see that file's own header for why this exists. Only ever intervenes
// when the DEFAULT resolver already failed on a relative specifier with no
// extension; every other specifier (bare package names, already-extensioned
// paths, non-relative specifiers) passes straight through unchanged.
//
// perf/hq-api pass (2026-09-15) addition: lib/personas.ts (the new test
// target) imports via the project's own "@/*" -> "./*" tsconfig path alias
// (e.g. "@/components/hq/palette", "@/lib/hq") -- a mapping only Next.js's
// bundler understood before now. Handled the SAME way as the pre-existing
// bare-relative-plus-.ts case just below: only ever intervenes after the
// default resolver has already failed, and only for a specifier starting
// with the literal "@/" prefix (never touches a real bare package name).
// Resolved relative to THIS file's own directory (tests/../ = dashboard
// root), matching tsconfig.json's "@/*": ["./*"] exactly.
const DASHBOARD_ROOT = new URL("../", import.meta.url);

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (err) {
    if (err?.code !== "ERR_MODULE_NOT_FOUND") throw err;
    const isBareRelative = (specifier.startsWith("./") || specifier.startsWith("../")) && !/\.[a-zA-Z0-9]+$/.test(specifier);
    if (isBareRelative) {
      return nextResolve(`${specifier}.ts`, context);
    }
    if (specifier.startsWith("@/")) {
      const target = new URL(specifier.slice(2), DASHBOARD_ROOT).href;
      const hasExt = /\.[a-zA-Z0-9]+$/.test(target);
      try {
        return await nextResolve(target, context);
      } catch (aliasErr) {
        if (!hasExt && aliasErr?.code === "ERR_MODULE_NOT_FOUND") {
          return nextResolve(`${target}.ts`, context);
        }
        throw aliasErr;
      }
    }
    throw err;
  }
}
