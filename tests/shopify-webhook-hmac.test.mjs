import { createHmac } from "node:crypto";
import assert from "node:assert/strict";
import { test } from "node:test";
import { verifyShopifyWebhookHmac } from "../app/lib/shopify-webhook-hmac.server.ts";

const secret = "test-only-in-memory-secret-not-production";
const payload = new TextEncoder().encode('{"id":42,"shop_domain":"example.myshopify.com"}');
const signed = createHmac("sha256", secret).update(payload).digest("base64");

test("valid Shopify HMAC is accepted", () => {
  assert.equal(verifyShopifyWebhookHmac(payload, signed, secret), true);
});
test("missing/empty/malformed HMAC is rejected", () => {
  for (const value of [null, "", "not-base64", "aaa", "="]) {
    assert.equal(verifyShopifyWebhookHmac(payload, value, secret), false);
  }
});
test("modified payload, wrong secret and different HMAC are rejected", () => {
  const tampered = new TextEncoder().encode('{"id":43,"shop_domain":"example.myshopify.com"}');
  assert.equal(verifyShopifyWebhookHmac(tampered, signed, secret), false);
  assert.equal(verifyShopifyWebhookHmac(payload, signed, "wrong-secret"), false);
  const different = createHmac("sha256", secret).update(tampered).digest("base64");
  assert.equal(verifyShopifyWebhookHmac(payload, different, secret), false);
});
