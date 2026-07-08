import type { ReactNode } from "react";
import { FileText, type LucideIcon } from "lucide-react";

import { Icon } from "./Icon";

interface DocumentPreviewCardProps {
  icon?: LucideIcon;
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/** Central on-screen frame around a printable document preview. */
export function DocumentPreviewCard({
  icon = FileText,
  title,
  subtitle,
  children,
}: DocumentPreviewCardProps) {
  return (
    <div className="document-preview">
      <div className="document-preview__head">
        <span className="document-preview__icon">
          <Icon icon={icon} size="sm" />
        </span>
        <div>
          <span className="document-preview__title">{title}</span>
          {subtitle ? <span className="document-preview__subtitle">{subtitle}</span> : null}
        </div>
      </div>
      <div className="document-preview__body">{children}</div>
    </div>
  );
}
