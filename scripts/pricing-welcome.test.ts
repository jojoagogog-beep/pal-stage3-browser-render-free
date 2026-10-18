import assert from "node:assert/strict";
import test from "node:test";
import { pricingWelcomeTarget } from "../app/lib/pricing-welcome";

for (const slug of ["pal-collection-image-ratio-guard", "pal-collection-sort-guard"]) {
  for (const path of [`/${slug}/welcome`, `/${slug}/app/welcome`]) {
    test(`${slug}: ${path} returns to the same app and preserves Shopify context`, () => {
      const query = "?plan_handle=monthly&shop=example.myshopify.com&host=test-host&embedded=1";
      assert.equal(pricingWelcomeTarget(`https://example.com${path}${query}`, slug), `/${slug}/app${query}`);
    });
  }
}
test("does not follow a return URL supplied in a query parameter", () => {
  const target = pricingWelcomeTarget("https://example.com/welcome?return_to=https://untrusted.invalid", "pal-collection-sort-guard");
  assert.equal(new URL(target, "https://example.com").origin, "https://example.com");
  assert.equal(new URL(target, "https://example.com").pathname, "/pal-collection-sort-guard/app");
});
test("has no welcome redirect loop with no parameters", () => {
  assert.equal(pricingWelcomeTarget("https://example.com/pal-collection-sort-guard/welcome", "pal-collection-sort-guard"), "/pal-collection-sort-guard/app");
});
