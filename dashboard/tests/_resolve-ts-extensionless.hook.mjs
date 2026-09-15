// The actual resolve hook registered by resolve-ts-extensionless.loader.mjs
// -- see that file's own header for why this exists. Only ever intervenes
// when the DEFAULT resolver already failed on a relative specifier with no
// extension; every other specifier (bare package names, already-extensioned
// paths, non-relative specifiers) passes straight through unchanged.
export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (err) {
    const isBareRelative = (specifier.startsWith("./") || specifier.startsWith("../")) && !/\.[a-zA-Z0-9]+$/.test(specifier);
    if (isBareRelative && err?.code === "ERR_MODULE_NOT_FOUND") {
      return nextResolve(`${specifier}.ts`, context);
    }
    throw err;
  }
}
