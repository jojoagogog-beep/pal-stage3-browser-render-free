import { createHmac, timingSafeEqual } from "node:crypto";

// Shopify signs the exact request body using the app's API secret.
// Never log or return the signing secret, raw HMAC, or webhook payload.
export function verifyShopifyWebhookHmac(
  body: Uint8Array,
  header: string | null,
  secret: string,
): boolean {
  if (!secret || !header || !/^[A-Za-z0-9+/]{43}=$/.test(header)) return false;
  const expected = createHmac("sha256", secret).update(body).digest();
  const actual = Buffer.from(header, "base64");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
