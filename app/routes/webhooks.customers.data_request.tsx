import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  if (!request.headers.get("X-Shopify-Hmac-Sha256")) {
    return new Response(null, { status: 401 });
  }
  try {
    await authenticate.webhook(request);
  } catch (error) {
    if (error instanceof Response && (error.status === 400 || error.status === 401)) {
      return new Response(null, { status: 401 });
    }
    throw error;
  }
  return new Response(null, { status: 200 });
};
