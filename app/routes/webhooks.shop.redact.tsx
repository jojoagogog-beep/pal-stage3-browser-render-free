import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import db from "../db.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  if (!request.headers.get("X-Shopify-Hmac-Sha256")) {
    return new Response(null, { status: 401 });
  }
  let shop: string;
  try {
    ({ shop } = await authenticate.webhook(request));
  } catch (error) {
    if (error instanceof Response && (error.status === 400 || error.status === 401)) {
      return new Response(null, { status: 401 });
    }
    throw error;
  }
  await db.session.deleteMany({ where: { shop } });
  return new Response(null, { status: 200 });
};
