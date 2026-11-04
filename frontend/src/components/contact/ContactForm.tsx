"use client";

import { useState, type FormEvent } from "react";
import { submitEnquiry } from "@/lib/api";
import { useSettings } from "../SettingsProvider";
import { errorText } from "../auth/messages";
import { interestOptions } from "./interests";

// The Consultation booking form of the Contact page. Works without signing in.
export default function ContactForm() {
  const { licence } = useSettings();
  const options = interestOptions(licence);
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [interest, setInterest] = useState("");
  const [date, setDate] = useState("");
  const [message, setMessage] = useState("");
  // Hidden from people; simple bots fill it in, and then nothing is saved.
  const [website, setWebsite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!name.trim()) return setError("Please enter your full name.");
    if (!contact.trim()) return setError("Please enter your email or phone.");
    setBusy(true);
    try {
      await submitEnquiry({ name, contact, interest: interest || options[0].value, preferred_date: date, message, website });
      setSent(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="msg" role="status">
        Thank you! We received your enquiry and will contact you soon.
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void send(e)} noValidate>
      <input name="n" placeholder="Full name" aria-label="Full name" required value={name} onChange={(e) => setName(e.target.value)} />
      <input name="e" placeholder="Email or phone" aria-label="Email or phone" required value={contact} onChange={(e) => setContact(e.target.value)} />
      <select aria-label="Interest" value={interest || options[0].value} onChange={(e) => setInterest(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <input
        name="website"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        value={website}
        onChange={(e) => setWebsite(e.target.value)}
        style={{ position: "absolute", left: "-10000px", width: 1, height: 1, opacity: 0 }}
      />
      <input
        type="date"
        aria-label="Preferred date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
      />
      <textarea placeholder="Contact form: tell us your question" aria-label="Message" value={message} onChange={(e) => setMessage(e.target.value)}></textarea>
      <p className="err" role="alert">
        {error}
      </p>
      <button className="btn" type="submit" disabled={busy}>
        Send
      </button>
    </form>
  );
}
