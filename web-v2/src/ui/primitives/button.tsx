/**
 * Summary: Provides the shared semantic button primitive.
 * Why: Keeps action hierarchy, touch targets, and ref behavior consistent.
 */
import { forwardRef, type ButtonHTMLAttributes } from "react";

import styles from "./button.module.css";

type ButtonVariant = "primary" | "secondary" | "quiet";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  iconOnly?: boolean;
  variant?: ButtonVariant;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      iconOnly = false,
      type = "button",
      variant = "secondary",
      ...props
    },
    ref,
  ) {
    const classes = [
      styles.button,
      styles[variant],
      iconOnly ? styles.iconOnly : undefined,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return <button {...props} className={classes} ref={ref} type={type} />;
  },
);
