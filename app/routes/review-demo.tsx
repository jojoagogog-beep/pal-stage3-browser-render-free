import { useSearchParams } from "react-router";
import { CollectionSortDashboard } from "../components/collection-sort-dashboard";
import { auditCollections } from "../lib/collection-sort-audit";
import { automaticDemoCollections, demoCollections } from "../lib/demo-catalog";

function source(state: string) {
  if (state === "manual") return demoCollections.filter((c) => c.sortOrder === "MANUAL");
  if (state === "automatic") return automaticDemoCollections();
  if (state === "best") return demoCollections.filter((c) => c.sortOrder === "BEST_SELLING");
  if (state === "price") return demoCollections.filter((c) => c.sortOrder === "PRICE_ASC");
  return demoCollections;
}

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "overview";
  return (
    <CollectionSortDashboard
      audit={auditCollections(source(state))}
      shopDomain="sample-shop.myshopify.com"
      shopName="PAL Sample Catalog"
      scannedAt="Oct 2, 2026, 1:20 PM UTC"
      coverageLimited={state === "limit"}
      showExport={false}
      demo
    />
  );
}
