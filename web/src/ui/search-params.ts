/**
 * Summary: Shares byte-identical leaf helpers for reading and writing optional URL search parameters.
 * Why: Keeps feature-local URL filter hooks free of duplicated selection and optional-set/delete logic.
 */
export function selectedValue<Value extends string>(
  rawValue: string | null,
  options: readonly Value[],
): Value | undefined {
  return options.find((option) => option === rawValue);
}

export function optionalValue(rawValue: string | null) {
  return rawValue === null || rawValue.length === 0 ? undefined : rawValue;
}

export function setOptionalParameter(
  searchParams: URLSearchParams,
  name: string,
  value: string | undefined,
) {
  if (value === undefined || value.length === 0) {
    searchParams.delete(name);
    return;
  }
  searchParams.set(name, value);
}
