"use client";

import { useState } from "react";
import { enrol, isApiError, updateMyProfile, type ApplicantAccount, type Course, type PayStart, type PaymentMethod } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import Modal from "../Modal";
import PaymentCheckout from "../payment/PaymentCheckout";

// Country choices from the reference Enrol form.
const COUNTRIES = ["Bangladesh", "India", "Nepal", "Pakistan", "Sri Lanka", "Other"];

type EnrolDialogProps = {
  course: Course;
  account: ApplicantAccount;
  onClose: () => void;
  onDone: (payment: PayStart) => void;
};

// "Enrol in <course>" (#buy and openBuy() in the reference) with the shared checkout.
export default function EnrolDialog({ course, account, onClose, onDone }: EnrolDialogProps) {
  const [name, setName] = useState(account.name);
  const [phone, setPhone] = useState(account.phone);
  const [email, setEmail] = useState(account.email ?? "");
  const [country, setCountry] = useState(COUNTRIES.includes(account.country) ? account.country : "Bangladesh");
  const [education, setEducation] = useState(account.education);

  // The details are saved to the profile first, then the course is paid for.
  async function pay(method: PaymentMethod, manualRef?: string): Promise<PayStart> {
    await updateMyProfile("course", { name, phone, country, education, email });
    try {
      return await enrol(course.slug, { method, phone, manual_ref: manualRef });
    } catch (error) {
      if (isApiError(error) && error.code === "CONFLICT") {
        throw new Error("You already have this course or a payment waiting for verification.");
      }
      throw error;
    }
  }

  return (
    <Modal open title={"Enrol in " + course.title} onClose={onClose}>
      <p className="sub">{formatMoney(course.price_poisha)} · one-time payment</p>
      <div style={{ display: "grid", gap: 14, marginBottom: 14 }}>
        <input name="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" aria-label="Full name" autoComplete="name" />
        <input
          name="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email (optional, for your receipt)"
          aria-label="Email (optional)"
          autoComplete="email"
        />
        <input
          name="phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="Mobile number (01XXXXXXXXX)"
          aria-label="Mobile number"
          inputMode="tel"
          autoComplete="tel"
        />
        <select name="country" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country">
          {COUNTRIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <input
          name="education"
          value={education}
          onChange={(e) => setEducation(e.target.value)}
          placeholder="Education or occupation"
          aria-label="Education or occupation"
        />
      </div>
      <PaymentCheckout amount_poisha={course.price_poisha} purpose={"Course: " + course.title} onPay={pay} onDone={onDone} />
    </Modal>
  );
}
