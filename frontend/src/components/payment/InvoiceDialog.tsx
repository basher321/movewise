"use client";

import Image from "next/image";
import type { Invoice } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { MODULE_UI } from "../auth/modules";
import Modal from "../Modal";
import { useSettings } from "../SettingsProvider";

type InvoiceDialogProps = {
  invoice: Invoice | null;
  open: boolean;
  onClose: () => void;
};

// The original logo from F01, used when Settings has no logo.
const DEFAULT_LOGO = "/logo.png";

// One invoice (invHtml() and openInv() in the reference). Print shows only the invoice.
// The company details are the ones saved on the invoice when it was issued.
export default function InvoiceDialog({ invoice, open, onClose }: InvoiceDialogProps) {
  const { settings } = useSettings();
  if (!invoice) return null;
  const company = invoice.company.name;
  const logo = settings?.logo_url || DEFAULT_LOGO;
  const refunded = invoice.status === "refunded";
  const amount = formatMoney(invoice.amount_poisha);

  function print() {
    document.body.classList.add("printing");
    const done = () => {
      document.body.classList.remove("printing");
      window.removeEventListener("afterprint", done);
    };
    window.addEventListener("afterprint", done);
    window.print();
  }

  return (
    <Modal open={open} label="Invoice" onClose={onClose}>
      <div style={{ marginTop: 8 }}>
        <div className="inv-p">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
            <Image
              src={logo}
              alt={company}
              width={70}
              height={48}
              unoptimized
              style={{ width: "auto", height: 48, background: "#F5F5F5", borderRadius: 10, padding: "2px 8px" }}
            />
            <div style={{ textAlign: "right" }}>
              <b style={{ fontSize: 24 }}>INVOICE</b>
              <br />
              {invoice.no}
              <br />
              {formatDate(invoice.issued_at)}
            </div>
          </div>
          <p style={{ margin: "18px 0 0" }}>
            <b>Billed to</b>
            <br />
            {invoice.name}
            <br />
            {invoice.email}
            <br />
            {MODULE_UI[invoice.module].name}
          </p>
          <table>
            <tbody>
              <tr>
                <th>Description</th>
                <th>Amount</th>
              </tr>
              <tr>
                <td>{invoice.description}</td>
                <td>{amount}</td>
              </tr>
              <tr>
                <td>
                  <b>Total paid</b>
                </td>
                <td>
                  <b>{amount}</b>
                </td>
              </tr>
            </tbody>
          </table>
          <p style={{ margin: 0 }}>
            Status:{" "}
            {refunded ? <b style={{ color: "#DC2626" }}>REFUNDED</b> : <b style={{ color: "#16A34A" }}>PAID</b>} · {invoice.method}
          </p>
          <p style={{ margin: "14px 0 0", fontSize: 13, color: "#55607A" }}>
            {[company, invoice.company.address, invoice.company.email, invoice.company.vat_bin ? "VAT BIN " + invoice.company.vat_bin : ""]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {invoice.company.footer ? <p style={{ margin: "8px 0 0", fontSize: 13, color: "#55607A" }}>{invoice.company.footer}</p> : null}
        </div>
      </div>
      <div className="cr">
        <button className="btn" type="button" onClick={print}>
          Print / Save as PDF
        </button>
      </div>
    </Modal>
  );
}
