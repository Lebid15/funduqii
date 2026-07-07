import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "./Button";

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  labels: {
    previous: string;
    next: string;
    /** Already-formatted "Page x of y" string. */
    status: string;
  };
}

/**
 * Central server-driven pagination. The chevrons mirror automatically in RTL
 * via the `.icon-flip` utility.
 */
export function Pagination({
  page,
  totalPages,
  onPageChange,
  labels,
}: PaginationProps) {
  if (totalPages <= 1) {
    return null;
  }
  return (
    <nav className="pagination" aria-label={labels.status}>
      <span className="pagination__info">{labels.status}</span>
      <div className="pagination__controls">
        <Button
          variant="secondary"
          size="sm"
          icon={ChevronLeft}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          {labels.previous}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          iconEnd={ChevronRight}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          {labels.next}
        </Button>
      </div>
    </nav>
  );
}
