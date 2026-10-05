import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  // Shopify's automated requirement check expects an explicit 401 for
  // missing/invalid webhook HMAC rather than the framework's generic 400.
  if (!request.headers.get("X-Shopify-Hmac-Sha256")) {
    return new Response(null, { status: 401 });
  }
  await authenticate.webhook(request);
  return new Response(null, { status: 200 });
};
