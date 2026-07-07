import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** Cell renderer; defaults to the row value at `key` when omitted. */
  render?: (row: T) => ReactNode;
  align?: "start" | "end";
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  /** Accessible caption for the table (translated). */
  caption: string;
}

/**
 * Central table. Always wrapped in a horizontal-scroll container so it never
 * breaks the layout on small screens (see `.table-scroll`).
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
}: DataTableProps<T>) {
  return (
    <div className="table-scroll">
      <table className="table">
        <caption className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
          {caption}
        </caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={column.align === "end" ? { textAlign: "end" } : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  style={
                    column.align === "end" ? { textAlign: "end" } : undefined
                  }
                >
                  {column.render
                    ? column.render(row)
                    : String((row as Record<string, unknown>)[column.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
