import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import db from "../db.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  // Shopify's automated requirement check expects an explicit 401 for
  // missing/invalid webhook HMAC rather than the framework's generic 400.
  if (!request.headers.get("X-Shopify-Hmac-Sha256")) {
    return new Response(null, { status: 401 });
  }
  const { shop } = await authenticate.webhook(request);
  await db.session.deleteMany({ where: { shop } });
  return new Response(null, { status: 200 });
};
