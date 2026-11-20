import { whatsappLink } from "@/lib/admin/whatsapp";

// Opens a WhatsApp chat with a greeting typed; shown only when the phone number is usable.
export default function WhatsAppLink({ phone, name }: { phone?: string | null; name: string }) {
  const href = whatsappLink(phone, "Dear " + name + ",");
  if (!href) return null;
  return (
    <a className="lk" href={href} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
      WhatsApp
    </a>
  );
}
