// Click-to-chat links: WhatsApp opens with the message typed and a staff member presses Send.
// The number rules match international() in backend/app/notify/whatsapp.py.

function internationalNumber(phone: string): string | null {
  const digits = phone.replace(/[\s()-]/g, "");
  if (/^01[3-9]\d{8}$/.test(digits)) return "88" + digits;
  if (/^\+?8801[3-9]\d{8}$/.test(digits)) return digits.replace("+", "");
  if (/^\+[1-9]\d{7,14}$/.test(digits)) return digits.slice(1);
  return null;
}

export function whatsappLink(phone: string | null | undefined, message = ""): string | null {
  const number = phone ? internationalNumber(phone) : null;
  if (!number) return null;
  const text = message.trim();
  return "https://wa.me/" + number + (text ? "?text=" + encodeURIComponent(text) : "");
}
