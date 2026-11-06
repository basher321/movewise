"use client";

import { useState } from "react";
import { COUNTRY_FLAGS, payApplicationFee, type AppModule, type PayStart, type PaymentMethod } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import Modal from "../Modal";
import PaymentCheckout from "../payment/PaymentCheckout";

type FeeDialogProps = {
  module: AppModule;
  applicationId: string;
  itemName: string;
  country: string;
  fee_poisha: number;
  phone: string;
  onClose: () => void;
  onDone: (payment: PayStart) => void;
  // Self Apply shows its own fee name; the application fee is the default.
  feeName?: string;
};

// The "Application fee" dialog (#fee and openFee() in the reference) with the shared checkout.
export default function FeeDialog({
  module,
  applicationId,
  itemName,
  country,
  fee_poisha,
  phone: initialPhone,
  onClose,
  onDone,
  feeName,
}: FeeDialogProps) {
  const [phone, setPhone] = useState(initialPhone);

  // The api checks the mobile number and the payment rules.
  function pay(method: PaymentMethod, manualRef?: string): Promise<PayStart> {
    return payApplicationFee(module, applicationId, { method, phone, manual_ref: manualRef });
  }

  return (
    <Modal open title={feeName ?? "Application fee"} onClose={onClose}>
      <p className="sub">
        {itemName} · {COUNTRY_FLAGS[country] ? COUNTRY_FLAGS[country] + " " : ""}
        {country}
      </p>
      <div className="card" style={{ marginBottom: 16, padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <span style={{ color: "var(--muted)", fontWeight: 600 }}>{feeName ?? "Application processing fee"}</span>
          <b style={{ font: "700 26px var(--font-sora)" }}>{formatMoney(fee_poisha)}</b>
        </div>
      </div>
      <input
        name="phone"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        placeholder="Your mobile number (01XXXXXXXXX)"
        aria-label="Mobile number"
        inputMode="tel"
        autoComplete="tel"
        style={{ marginBottom: 14 }}
      />
      <PaymentCheckout amount_poisha={fee_poisha} purpose={(feeName ?? "Application fee") + ": " + itemName} onPay={pay} onDone={onDone} />
    </Modal>
  );
}
