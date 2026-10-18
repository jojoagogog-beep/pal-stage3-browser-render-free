// Shopify App Pricing return parameters are routing context, never proof of payment.
// Access remains protected by the existing authenticated app loader.
export function pricingWelcomeTarget(requestUrl: string, slug: string): string {
  const url = new URL(requestUrl);
  return "/" + encodeURIComponent(slug) + "/app" + url.search;
}
