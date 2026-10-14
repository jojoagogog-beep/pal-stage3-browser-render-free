import { useSearchParams } from "react-router";
import type { ActionFunctionArgs } from "react-router";
import { VariantImageDashboard } from "./components/variant-image-dashboard";
import { demoCatalogFor } from "./lib/demo-catalog";
import {
  auditCatalog,
  buildAffectedProductsCsv,
} from "./lib/variant-image-audit";

export const action = async ({ request }: ActionFunctionArgs) => {
  const state = new URL(request.url).searchParams.get("state") || "overview";
  const csv = buildAffectedProductsCsv(
    auditCatalog(demoCatalogFor(state)),
    "",
  );
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition":
        'attachment; filename="variant-image-guard-sample.csv"',
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "overview";
  return (
    <VariantImageDashboard
      audit={auditCatalog(demoCatalogFor(state))}
      shopName="PAL Sample Catalog"
      scannedAt="Sep 30, 2026, 09:30 UTC"
      coverageLimited={state === "limit"}
      demo
    />
  );
}
