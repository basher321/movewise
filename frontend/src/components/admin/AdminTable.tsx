import type { ReactNode } from "react";

export type Column<T> = {
  head: string;
  cell: (row: T) => ReactNode;
  right?: boolean;
};

type AdminTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty: string;
};

// The reference tbl(): a .xt table in a .tw wrapper, or the muted empty text.
export default function AdminTable<T>({ columns, rows, rowKey, empty }: AdminTableProps<T>) {
  if (!rows.length) return <p style={{ color: "var(--muted)", margin: 0 }}>{empty}</p>;
  return (
    <div className="tw">
      <table className="xt">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} style={c.right ? { textAlign: "right" } : undefined}>
                {c.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c, i) => (
                <td key={i} style={c.right ? { textAlign: "right" } : undefined}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
