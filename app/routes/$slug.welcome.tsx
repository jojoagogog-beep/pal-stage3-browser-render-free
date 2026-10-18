import type { LoaderFunctionArgs } from "react-router";
import { redirect } from "react-router";
import { getSlug } from "../multi-shopify.server";
import { pricingWelcomeTarget } from "../lib/pricing-welcome";

export function loader({ request }: LoaderFunctionArgs) {
  const slug = getSlug(request);
  return redirect(pricingWelcomeTarget(request.url, slug), {
    headers: { "Cache-Control": "no-store" },
  });
}

export default function Welcome() { return null; }
