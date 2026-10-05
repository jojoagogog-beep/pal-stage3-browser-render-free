import type { LoaderFunctionArgs } from "react-router";
import { redirect } from "react-router";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  const url = new URL(request.url);
  const planHandle = url.searchParams.get("plan_handle") || "unknown";

  const target = new URL("/app", url.origin);
  target.searchParams.set("plan", planHandle);
  return redirect(target.pathname + target.search);
};

export default function Welcome() {
  return null;
}
