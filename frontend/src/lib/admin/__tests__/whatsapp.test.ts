import { describe, expect, it } from "vitest";
import { whatsappLink } from "../whatsapp";

describe("whatsappLink", () => {
  it("turns Bangladesh and international numbers into wa.me links", () => {
    expect(whatsappLink("01712345678")).toBe("https://wa.me/8801712345678");
    expect(whatsappLink("017 1234-5678")).toBe("https://wa.me/8801712345678");
    expect(whatsappLink("8801712345678")).toBe("https://wa.me/8801712345678");
    expect(whatsappLink("+8801712345678")).toBe("https://wa.me/8801712345678");
    expect(whatsappLink("+447911123456")).toBe("https://wa.me/447911123456");
  });

  it("types the message, encoded, keeping line breaks", () => {
    expect(whatsappLink("01712345678", "Dear Rahim & co,\n\nHello")).toBe(
      "https://wa.me/8801712345678?text=Dear%20Rahim%20%26%20co%2C%0A%0AHello",
    );
    expect(whatsappLink("01712345678", "   ")).toBe("https://wa.me/8801712345678");
  });

  it("gives no link without a usable number", () => {
    for (const bad of [null, undefined, "", "12345", "01212345678", "447911123456"]) expect(whatsappLink(bad)).toBeNull();
  });
});
