// Shopify's automated App Store check calls the shop/redact webhook under /app.
// Reuse the existing action: authenticate.webhook validates the request HMAC.
export { action } from "./webhooks.shop.redact";
