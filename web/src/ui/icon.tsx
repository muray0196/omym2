/**
 * Summary: Renders symbols from the single bundled local SVG icon set.
 * Why: Keeps icons offline, CSP-safe, and consistently accessible.
 */
import iconSpriteUrl from "../assets/icons/omym2-icons.svg";

export type IconName =
  | "arrow-right"
  | "check"
  | "close"
  | "command"
  | "info"
  | "menu"
  | "search"
  | "warning";

type IconProps = {
  name: IconName;
  label?: string;
};

export function Icon({ name, label }: IconProps) {
  return (
    <svg
      aria-hidden={label === undefined ? true : undefined}
      aria-label={label}
      focusable="false"
      role={label === undefined ? undefined : "img"}
      viewBox="0 0 24 24"
    >
      <use href={`${iconSpriteUrl}#${name}`} />
    </svg>
  );
}
