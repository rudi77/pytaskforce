import * as React from "react";
import { Field } from "@fluentui/react-components";

import { cn } from "@/lib/utils";

interface FormFieldProps {
  label: React.ReactNode;
  /**
   * Kept for backwards compatibility — Fluent ``<Field>`` derives the
   * label/input association from its slot, but most call sites still
   * pass ``htmlFor`` alongside an explicit ``id`` on the child input.
   * Forwarded to the ``label`` slot so screen readers see the same
   * ``for`` attribute as before.
   */
  htmlFor?: string;
  description?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  className?: string;
  required?: boolean;
}

/**
 * Thin wrapper around Fluent v9 ``<Field>`` that preserves the
 * shadcn-era FormField API (``label``, ``htmlFor``, ``description``,
 * ``error``, ``required``). Field handles label-above-input stacking,
 * full-width slot and validation styling natively, fixing the
 * inline-label regression from PR #441 (see issue #448).
 */
export function FormField({
  label,
  htmlFor,
  description,
  error,
  children,
  className,
  required,
}: FormFieldProps) {
  // Wrap in fragments — React.ReactNode allows booleans, but Fluent's
  // slot props reject them (slot expects ReactElement | string | number
  // | Iterable, not bool). A Fragment guarantees a single ReactElement.
  const labelSlot: React.ReactElement = (
    <>{label as React.ReactNode}</>
  );
  const hintSlot: React.ReactElement | undefined =
    !error && description ? <>{description as React.ReactNode}</> : undefined;
  return (
    <Field
      className={cn(className)}
      label={htmlFor ? { children: labelSlot, htmlFor } : labelSlot}
      required={required}
      hint={hintSlot}
      validationMessage={error}
      validationState={error ? "error" : "none"}
    >
      {children}
    </Field>
  );
}
