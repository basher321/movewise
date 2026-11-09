"use client";

import { useState, type ChangeEvent } from "react";
import { commitImport, downloadImportTemplate, MAX_IMPORT_BYTES, previewImport, type AdminUser, type ImportKind, type ImportReport, type ImportRow, type ImportRowStatus, type LicenceView } from "@/lib/api";
import { allowedImportKinds } from "@/lib/admin/tabs";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

const KIND_LABELS: Record<ImportKind, string> = {
  university: "Universities",
  vacancy: "Job vacancies",
  visa: "Visa programmes",
};

const STATUS_BADGE: Record<ImportRowStatus, [string, string]> = {
  new: ["bd ok", "New"],
  skipped: ["bd", "Skipped"],
  error: ["bd no", "Error"],
};

const XLSX_TYPE = ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

type Props = { admin: AdminUser; licence: LicenceView; toast: ShowToast; onSignedOut: () => void };

function plural(count: number): string {
  return count + (count === 1 ? " item" : " items");
}

// Excel upload of listings (B23). Not in the reference: it follows the admin tab style
// (TabPage, .seg, .card, .fl fields, .xt table, .bd badges).
export default function ImportTab({ admin, licence, toast, onSignedOut }: Props) {
  const kinds = allowedImportKinds(admin, licence);
  const [chosen, setChosen] = useState<ImportKind | null>(kinds[0] ?? null);
  const kind = chosen && kinds.includes(chosen) ? chosen : (kinds[0] ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [preview, setPreview] = useState<ImportReport | null>(null);
  const [result, setResult] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function clearFile() {
    setFile(null);
    setFileKey((k) => k + 1);
    setPreview(null);
  }

  function chooseKind(next: ImportKind) {
    setChosen(next);
    clearFile();
    setResult(null);
    setError("");
  }

  function chooseFile(e: ChangeEvent<HTMLInputElement>) {
    setFile(e.target.files?.[0] ?? null);
    setPreview(null);
    setResult(null);
    setError("");
  }

  function fail(err: unknown) {
    handleFailure(err, () => setError(errorText(err)), onSignedOut);
  }

  async function check() {
    if (busy || !kind) return;
    setError("");
    setResult(null);
    if (!file) return setError("Please choose a file.");
    if (file.size > MAX_IMPORT_BYTES) return setError("The file must be 5 MB or smaller.");
    setBusy(true);
    try {
      setPreview(await previewImport(kind, file));
    } catch (err) {
      setPreview(null);
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (busy || !kind || !file) return;
    setError("");
    setBusy(true);
    try {
      const done = await commitImport(kind, file);
      setResult(done);
      clearFile();
      toast(plural(done.new_count) + " added.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  const report = result ?? preview;

  return (
    <TabPage title="Excel upload" sub="Add many listings at once from an Excel file. Items that already exist are skipped and never changed.">
      {kind === null ? (
        <div className="banner no">You do not have access to any section with Excel upload.</div>
      ) : (
        <>
          <div className="seg" style={{ maxWidth: kinds.length * 190, gridTemplateColumns: "repeat(auto-fit,minmax(min(170px,100%),1fr))", marginBottom: 20, borderRadius: 22 }}>
            {kinds.map((k) => (
              <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => chooseKind(k)}>
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>1. Download the template</h3>
            <p className="sub" style={{ marginTop: 0 }}>
              Fill in one item per row. Columns marked with * are required. The Instructions sheet explains every column.
            </p>
            <button className="btn ghost sm" type="button" onClick={() => downloadImportTemplate(kind)}>
              Download template
            </button>
          </div>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>2. Upload the filled file</h3>
            <label className="fl" style={{ marginTop: 12 }}>
              <span>Excel file (.xlsx, up to 5 MB and 1000 rows)</span>
              <input key={fileKey} type="file" accept={XLSX_TYPE} onChange={chooseFile} />
            </label>
            <p className="err" role="alert">
              {error}
            </p>
            <button className="btn sm" type="button" disabled={busy || !file} onClick={() => void check()}>
              {busy && !preview ? "Checking…" : "Check file"}
            </button>
          </div>
          {report ? (
            <div className="card">
              <h3>{result ? "3. Result" : "3. Check and confirm"}</h3>
              {result ? (
                <div className="banner ok">
                  {plural(result.new_count)} added to {KIND_LABELS[result.kind]}.
                </div>
              ) : (
                <p className="sub" style={{ marginTop: 0 }}>
                  Nothing has been saved yet.
                </p>
              )}
              <p style={{ margin: "0 0 12px" }}>
                <span className="bd ok">
                  {report.new_count} {result ? "added" : "new"}
                </span>
                <span className="bd">{report.skipped_count} skipped</span>
                <span className="bd no">{report.error_count} with errors</span>
              </p>
              <AdminTable
                rows={report.rows}
                rowKey={(r: ImportRow) => String(r.row_number)}
                empty="No rows."
                columns={[
                  { head: "Row", cell: (r) => r.row_number },
                  { head: "Item", cell: (r) => <span style={{ overflowWrap: "anywhere" }}>{r.label}</span> },
                  {
                    head: "Status",
                    cell: (r) => {
                      const [cls, text] = result && r.status === "new" ? ["bd ok", "Added"] : STATUS_BADGE[r.status];
                      return <span className={cls}>{text}</span>;
                    },
                  },
                  {
                    head: "Message",
                    cell: (r) => (
                      <span style={{ overflowWrap: "anywhere" }}>
                        {r.message}
                        {r.warnings.map((w) => (
                          <small key={w}>{w}</small>
                        ))}
                      </span>
                    ),
                  },
                ]}
              />
              {preview && !result ? (
                <div className="cr" style={{ margin: "16px 0 0" }}>
                  <button className="btn sm" type="button" disabled={busy || preview.new_count === 0} onClick={() => void confirm()}>
                    {busy ? "Adding…" : "Add " + plural(preview.new_count)}
                  </button>
                  <button className="btn ghost sm" type="button" disabled={busy} onClick={clearFile}>
                    Cancel
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </TabPage>
  );
}
