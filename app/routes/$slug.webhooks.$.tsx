import type { ActionFunctionArgs } from "react-router";
import db from "../db.server";
import { appEnvNames } from "../rules/app-env-names";
import { getShopify, getSlug } from "../multi-shopify.server";
import { verifyShopifyWebhookHmac } from "../lib/shopify-webhook-hmac.server";
import { deleteFilterConfig } from "../special/filter-integrity/filter-config.server";

export async function action({ request }: ActionFunctionArgs) {
  const slug = getSlug(request);
  const names = appEnvNames[slug as keyof typeof appEnvNames];
  const signingSecret = process.env[names.secret];
  if (!signingSecret) {
    // Shopify retries a failed delivery. Never acknowledge it while the
    // app's production secret is missing or not yet provisioned.
    return new Response("Webhook not configured", { status: 503 });
  }

  const contentType = request.headers.get("content-type") || "";
  if (!/^application\/json(?:\s*;|$)/i.test(contentType)) {
    return new Response("Unsupported webhook content type", { status: 415 });
  }

  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > 2 * 1024 * 1024) {
    return new Response("Webhook too large", { status: 413 });
  }

  const rawBody = new Uint8Array(await request.clone().arrayBuffer());
  if (!verifyShopifyWebhookHmac(
    rawBody,
    request.headers.get("x-shopify-hmac-sha256"),
    signingSecret,
  )) {
    // Shopify's mandatory compliance checks require HTTP 401, not 400.
    return new Response("Invalid webhook signature", { status: 401 });
  }

  const { shop, topic, payload } = await getShopify(slug).authenticate.webhook(request);
  if (topic === "APP_UNINSTALLED" || topic === "SHOP_REDACT") {
    // Remove persisted merchant preferences as well as Shopify sessions.
    // The filter configuration table is scoped by shop and used only by this app.
    if (slug === "pal-filter-integrity-guard") {
      await deleteFilterConfig(shop);
    }
    await db.session.deleteMany({
      where: { shop, id: { startsWith: slug + ":" } },
    });
  }
  if (topic === "APP_SCOPES_UPDATE") {
    const current = (payload as any)?.current;
    if (!Array.isArray(current) || !current.every((v: unknown) => typeof v === "string")) {
      return new Response("Invalid scope payload", { status: 400 });
    }
    await db.session.updateMany({
      where: { shop, id: { startsWith: slug + ":" } },
      data: { scope: current.join(",") },
    });
  }
  // This catalog-only app does not store any customer's personal data.
  // CUSTOMER_* compliance topics therefore require no customer-data mutation.
  return new Response(null, { status: 200 });
}
