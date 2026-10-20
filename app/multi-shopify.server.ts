import "@shopify/shopify-app-react-router/adapters/node";
import { ApiVersion, AppDistribution, shopifyApp } from "@shopify/shopify-app-react-router/server";
import { PrismaSessionStorage } from "@shopify/shopify-app-session-storage-prisma";
import prisma from "./db.server";
import { appEnvNames } from "./rules/app-env-names";

const origin = process.env.BATCH50_PUBLIC_ORIGIN || process.env.BATCH50_ORIGIN || "";
const baseStorage = new PrismaSessionStorage(prisma);
const instances = new Map<string, ReturnType<typeof shopifyApp>>();

class ScopedSessionStorage {
  constructor(private readonly slug: string) {}
  private key(id: string) { return this.slug + ":" + id; }
  private unkey(id: string) { return id.startsWith(this.slug + ":") ? id.slice(this.slug.length + 1) : id; }
  async storeSession(session: any) {
    const original = session.id;
    session.id = this.key(original);
    try { return await baseStorage.storeSession(session); }
    finally { session.id = original; }
  }
  async loadSession(id: string) {
    const session = await baseStorage.loadSession(this.key(id));
    if (session) (session as any).id = this.unkey(session.id);
    return session;
  }
  async deleteSession(id: string) { return baseStorage.deleteSession(this.key(id)); }
  async deleteSessions(ids: string[]) { return baseStorage.deleteSessions(ids.map((id) => this.key(id))); }
  async findSessionsByShop(shop: string) {
    const rows = await prisma.session.findMany({
      where: { shop, id: { startsWith: this.slug + ":" } },
      take: 25,
      orderBy: [{ expires: "desc" }],
      select: { id: true },
    });
    const sessions = await Promise.all(rows.map((r) => baseStorage.loadSession(r.id)));
    return sessions.filter(Boolean).map((s: any) => { s.id = this.unkey(s.id); return s; });
  }
  async isReady() { return baseStorage.isReady(); }
}

export function isKnownSlug(slug: string) {
  return Object.prototype.hasOwnProperty.call(appEnvNames, slug);
}

export function getShopify(slug: string) {
  const names = appEnvNames[slug as keyof typeof appEnvNames];
  if (!names) throw new Response("Unknown app", { status: 404 });
  const existing = instances.get(slug);
  if (existing) return existing;
  const apiKey = process.env[names.key];
  const apiSecretKey = process.env[names.secret];
  // The reviewed collection apps can move to an approved permanent hostname
  // independently, without interrupting the other gateway-hosted apps.
  // These two live app versions are registered on the permanent neutral
  // hostname. Keep Shopify's OAuth callback and embedded appUrl on exactly the
  // same origin regardless of optional Render environment overrides.
  // Paused review apps use the neutral permanent Shopify-hosted URL in their
  // staged app configuration. Keep OAuth/appUrl on the same origin as Shopify.
  const neutralReviewSlugs = new Set([
    "pal-filter-integrity-guard",
    // These three paused-review apps must use the exact same stable
    // origin as their released embedded app and OAuth callback URLs.
    "pal-seo-length-guard",
    "pal-duplicate-sku-guard",
    "pal-compare-at-price-guard",
    "pal-product-title-pattern-guard",
    "pal-description-accessibility-guard",
    "pal-price-ending-guard",
    "pal-variant-shipping-policy-guard",
    "pal-option-value-consistency-guard",
    "pal-product-type-consistency-guard",
    "pal-inventory-policy-consistency-guard",
    "pal-sku-format-consistency-guard",
    "pal-variant-tax-flag-guard",
    "pal-option-name-consistency-guard",
    "pal-collection-coverage-guard",
    "pal-empty-collection-guard",
    "pal-selling-plan-coverage-guard",
    "pal-customs-data-readiness-guard",
    "pal-tag-consistency-guard",
    "pal-unit-cost-coverage-guard",
    "pal-inventory-location-consistency-guard",
    "pal-inventory-location-secondary-guard",
    "pal-collection-rule-guard",
    "pal-rule-drift-guard",
    "pal-product-image-size-guard",
    "pal-product-tag-count-guard",
    "pal-product-handle-guard",
    "pal-product-image-aspect-guard",
    "pal-archived-stock-guard",
    "pal-negative-inventory-guard",
    "pal-variant-count-guard",
    "pal-draft-stock-guard",
    "pal-option-complexity-guard",
    "pal-seo-duplicate-guard",
    "pal-description-html-guard",
    "pal-duplicate-description-guard",
    "pal-title-length-guard",
    "pal-title-word-count-guard",
    "pal-title-digit-guard",
    "pal-title-trailing-mark-guard",
    "pal-title-leading-space-guard",
    "pal-variant-image-guard",
    "pal-variant-order-guard",
    "pal-feed-readiness-guard",
    "pal-import-row-integrity-guard",
  ]);
  const externalOrigin = slug === "pal-seo-bulk-fixer"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : neutralReviewSlugs.has(slug)
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-variant-sale-guard"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-vendor-name-consistency-guard"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-inventory-availability-guard"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-shipping-weight-integrity-guard"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-active-product-age-guard"
    ? process.env.PAL_AGE_PUBLIC_ORIGIN
    : [
      "pal-category-attribute-coverage-guard",
      "pal-collection-content-guard",
      "pal-product-description-guard",
      "pal-product-media-count-guard",
      "pal-stale-draft-product-guard",
    ].includes(slug)
    // Keep OAuth appUrl on the same stable hostname as the reviewed app URL.
    // A gateway origin here caused cross-host authorization redirects.
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-seo-fallback-readiness-guard"
    ? "https://pal-stage3-browser-free-shard1.onrender.com"
    : slug === "pal-product-image-alt-guard"
    ? process.env.PAL_ALT_PUBLIC_ORIGIN
    : slug === "pal-collection-image-ratio-guard"
    ? process.env.PAL_RATIO_PUBLIC_ORIGIN
    : slug === "pal-collection-sort-guard"
      ? process.env.PAL_SORT_PUBLIC_ORIGIN
      : undefined;
  const appOrigin = externalOrigin || origin;
  if (externalOrigin) {
    const url = new URL(externalOrigin);
    if (url.protocol !== "https:" || /(^|\.)shopify\.com$|(^|\.)myshopify\.com$|example|trycloudflare/i.test(url.hostname) || url.pathname !== "/") {
      throw new Error("Collection app origin must be a permanent compliant HTTPS hostname");
    }
  }
  if (!apiKey || !apiSecretKey || !appOrigin) throw new Error("Missing runtime app configuration for " + slug);
  const instance = shopifyApp({
    apiKey,
    apiSecretKey,
    apiVersion: ApiVersion.July26,
    scopes: slug === "pal-seo-bulk-fixer" ? ["read_products", "write_products", "write_files"]
      : (slug === "pal-inventory-location-consistency-guard" || slug === "pal-inventory-location-secondary-guard")
      ? ["read_products", "read_inventory", "read_locations"]
      : slug === "pal-variant-shipping-policy-guard"
      ? ["read_products", "read_inventory"]
      : ["pal-archived-stock-guard","pal-negative-inventory-guard","pal-draft-stock-guard"].includes(slug)
      ? ["read_products", "read_inventory"]
      : ["read_products"],
    appUrl: appOrigin,
    authPathPrefix: "/" + slug + "/auth",
    sessionStorage: new ScopedSessionStorage(slug) as any,
    distribution: AppDistribution.AppStore,
    future: { expiringOfflineAccessTokens: true },
  });
  instances.set(slug, instance);
  return instance;
}

export function getSlug(request: Request) {
  const slug = new URL(request.url).pathname.split("/").filter(Boolean)[0] || "";
  if (!isKnownSlug(slug)) throw new Response("Unknown app", { status: 404 });
  return slug;
}

export function apiKeyFor(slug: string) {
  const names = appEnvNames[slug as keyof typeof appEnvNames];
  const value = names ? process.env[names.key] : undefined;
  if (!value) throw new Response("Unknown app", { status: 404 });
  return value;
}
