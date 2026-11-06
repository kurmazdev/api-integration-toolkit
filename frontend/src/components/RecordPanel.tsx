import {
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Check,
  Braces,
  Database,
} from "lucide-react";
import type { Row } from "../types";
import { Badge, date } from "../ui";
type Props = {
  dataTab: string;
  setDataTab: (value: string) => void;
  preview: Row[] | null;
  rows: Row[];
  total: number;
  offset: number;
  onPage: (offset: number) => void;
};
export function RecordPanel({
  dataTab,
  setDataTab,
  preview,
  rows,
  total,
  offset,
  onPage,
}: Props) {
  return (
    <section className="panel data-panel">
      <div className="data-header">
        <div className="data-tabs" role="tablist" aria-label="Data view">
          <button
            role="tab"
            aria-selected={dataTab === "preview"}
            className={dataTab === "preview" ? "selected" : ""}
            onClick={() => setDataTab("preview")}
          >
            API preview
            {preview && <span className="count">{preview.length}</span>}
          </button>
          <button
            role="tab"
            aria-selected={dataTab === "records"}
            className={dataTab === "records" ? "selected" : ""}
            onClick={() => setDataTab("records")}
          >
            Synced records<span className="count">{total}</span>
          </button>
        </div>
        {dataTab === "records" && (
          <div className="export">
            <ArrowDownToLine size={14} />
            <a
              aria-disabled={!total}
              href={total ? "/api/export/csv" : undefined}
            >
              CSV
            </a>
            <span>/</span>
            <a
              aria-disabled={!total}
              href={total ? "/api/export/xlsx" : undefined}
            >
              Excel
            </a>
          </div>
        )}
      </div>
      {(dataTab === "preview" ? preview : rows)?.length ? (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th className="numeric">Amount</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {(dataTab === "preview" ? preview! : rows).map((row, i) => (
                  <tr key={row.id + i}>
                    <td>
                      <code>{row.id}</code>
                    </td>
                    <td>{row.name}</td>
                    <td>
                      <Badge status={row.status} />
                    </td>
                    <td className="numeric">{row.amount.toFixed(2)}</td>
                    <td className="muted">{date(row.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            {dataTab === "preview" ? (
              <>
                <span>
                  <Check size={13} />
                  Validated & normalized
                </span>
                <span>Preview only · nothing written</span>
              </>
            ) : (
              <>
                <span>
                  {offset + 1}–{Math.min(offset + 10, total)} of {total} records
                </span>
                <div>
                  <button
                    className="icon-button"
                    aria-label="Previous records"
                    disabled={!offset}
                    onClick={() => onPage(offset - 10)}
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Next records"
                    disabled={offset + 10 >= total}
                    onClick={() => onPage(offset + 10)}
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </>
            )}
          </div>
        </>
      ) : (
        <div className="empty">
          <span className="empty-icon">
            {dataTab === "preview" ? (
              <Braces size={23} />
            ) : (
              <Database size={23} />
            )}
          </span>
          <h3>
            {dataTab === "preview"
              ? preview
                ? "No matching records"
                : "Validate before you write"
              : "No synchronized records yet"}
          </h3>
          <p>
            {dataTab === "preview"
              ? "Test the connection to inspect normalized data here."
              : "Run a synchronization to store records in SQLite."}
          </p>
        </div>
      )}
    </section>
  );
}
