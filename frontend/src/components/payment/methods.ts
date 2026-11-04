import { PAYMENT_METHODS, type PaymentMethod, type PublicSettings } from "@/lib/api";

// Names shown to people (methods() and MANUAL in the reference). Nagad is paid inside SSLCommerz.
export const METHOD_NAMES: Record<PaymentMethod, string> = {
  sslcommerz: "SSLCommerz",
  bkash: "bKash",
  manual: "Bank transfer / office",
};

// The methods switched on in Settings, in the reference order.
export function enabledMethods(settings: PublicSettings | null): PaymentMethod[] {
  return settings ? PAYMENT_METHODS.filter((m) => settings.gateways[m].enabled) : [];
}
