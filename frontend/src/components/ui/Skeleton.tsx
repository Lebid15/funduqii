import type { CSSProperties } from "react";

import { cx } from "@/lib/utils";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  radius?: string;
  className?: string;
}

/** Central shimmer placeholder used while data loads (respects reduced motion). */
export function Skeleton({ width, height, radius, className }: SkeletonProps) {
  const style: CSSProperties = {
    width,
    height,
    borderRadius: radius,
  };
  return <span className={cx("skeleton", className)} style={style} aria-hidden="true" />;
}
