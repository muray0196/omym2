/**
 * Summary: Resolves values from coordinated closed frontend catalogs.
 * Why: Makes schema drift or corrupted enum data fail explicitly instead of inventing fallback UI.
 */
export function catalogValueOrThrow<Value extends string, Presentation>(
  catalogName: string,
  value: string,
  presentations: Readonly<Record<Value, Presentation>>,
): Presentation {
  const presentation = presentations[value as Value];
  if (presentation === undefined) {
    throw new Error(`Unknown ${catalogName} value: ${value}`);
  }
  return presentation;
}
