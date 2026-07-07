import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

type IconSize = "sm" | "md" | "lg";

const SIZE_PX: Record<IconSize, number> = { sm: 16, md: 18, lg: 22 };

interface IconProps {
  /** A lucide-react icon component (the single, central icon library). */
  icon: LucideIcon;
  size?: IconSize;
  className?: string;
  /**
   * Accessible label. Omit for purely decorative icons (they are hidden from
   * assistive tech); provide it when the icon is the only conveyor of meaning.
   */
  label?: string;
}

/**
 * Central icon wrapper. Standardizes size and stroke width across the whole
 * app so icons read as one consistent set. All UI icons go through here — no
 * emoji, no mixed icon sources.
 */
export function Icon({ icon: LucideCmp, size = "md", className, label }: IconProps) {
  return (
    <LucideCmp
      size={SIZE_PX[size]}
      strokeWidth={1.75}
      className={cx("icon", className)}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      focusable={false}
    />
  );
}
