import type { LoaderFunctionArgs } from "react-router";
import db from "../db.server";

export async function loader({ request }: LoaderFunctionArgs) {
  const configured = Boolean(
    process.env.SHOPIFY_API_KEY &&
    process.env.SHOPIFY_API_SECRET &&
    process.env.SHOPIFY_APP_URL?.startsWith("https://") &&
    !process.env.SHOPIFY_APP_URL?.includes(".trycloudflare.com")
  );
  if (!configured) {
    return Response.json(
      { status: "unavailable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  try {
    await db.session.count();
    return Response.json(
      { status: "ok" },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return Response.json(
      { status: "unavailable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
