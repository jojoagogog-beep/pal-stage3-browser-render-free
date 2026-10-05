import type { LoaderFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

export async function loader({ request }: LoaderFunctionArgs) {
  await authenticate.admin(request);
  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
      "Pragma": "no-cache",
    },
  });
}

export default function SessionTokenProbe() {
  return null;
}
