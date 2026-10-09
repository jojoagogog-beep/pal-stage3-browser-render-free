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
  const externalOrigin = slug === "pal-active-product-age-guard"
    ? process.env.PAL_AGE_PUBLIC_ORIGIN
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
    if (url.protocol !== "https:" || /shopify|example|trycloudflare/i.test(url.hostname) || url.pathname !== "/") {
      throw new Error("Collection app origin must be a permanent compliant HTTPS hostname");
    }
  }
  if (!apiKey || !apiSecretKey || !appOrigin) throw new Error("Missing runtime app configuration for " + slug);
  const instance = shopifyApp({
    apiKey,
    apiSecretKey,
    apiVersion: ApiVersion.July26,
    scopes: ["read_products"],
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
