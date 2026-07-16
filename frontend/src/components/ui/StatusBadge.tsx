import type { LucideIcon } from "lucide-react";

import { Badge, type BadgeTone, type BadgeVariant } from "./Badge";

interface StatusBadgeProps {
  /** Semantic tone — typically from a `*StatusTone` helper in `@/lib/format`. */
  tone: BadgeTone;
  /** Already-translated status label — typically from a `*StatusLabel` helper. */
  label: string;
  /** Optional leading icon so meaning is never conveyed by colour alone (WCAG). */
  icon?: LucideIcon;
  /** Visual weight. Defaults to the soft pill — identical to a raw `<Badge>`. */
  variant?: BadgeVariant;
  className?: string;
}

/**
 * Central domain-status pill. A THIN wrapper over {@link Badge} that standardises
 * turning a domain status into tone + (optional) icon + translated label —
 * mirroring {@link PaymentStatusBadge}, but generic across domains (reservation /
 * stay / room status, …). The tone + label come from the shared helpers in
 * `@/lib/format`; the caller passes the already-translated label so this stays
 * decoupled from any feature dictionary.
 *
 * With no `icon`/`variant` it renders EXACTLY like `<Badge tone={t}>{label}</Badge>`,
 * so migrating a hand-written status Badge to it is a no-op visually — while
 * giving one central place to later add per-domain icons. Raw {@link Badge}
 * stays available for non-status pills.
 */
export function StatusBadge({
  tone,
  label,
  icon,
  variant,
  className,
}: StatusBadgeProps) {
  return (
    <Badge tone={tone} variant={variant} icon={icon} className={className}>
      {label}
    </Badge>
  );
}
