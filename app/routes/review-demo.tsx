import { useSearchParams } from "react-router";
import { CollectionImageRatioDashboard } from "../components/collection-image-ratio-dashboard";
import { auditCollections } from "../lib/collection-image-ratio-audit";
import { demoCollections, readyDemoCollections } from "../lib/demo-catalog";

function source(state: string) {
  if (state === "ready") return readyDemoCollections();
  if (state === "wide") return demoCollections.filter((c) => ["6101","6103"].includes(c.legacyResourceId));
  if (state === "portrait") return demoCollections.filter((c) => ["6101","6104"].includes(c.legacyResourceId));
  if (state === "missing") return demoCollections.filter((c) => ["6101","6105"].includes(c.legacyResourceId));
  return demoCollections;
}

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "overview";
  return (
    <CollectionImageRatioDashboard
      audit={auditCollections(source(state))}
      shopDomain="sample-shop.myshopify.com"
      shopName="PAL Sample Catalog"
      scannedAt="Oct 2, 2026, 4:35 PM UTC"
      coverageLimited={state === "limit"}
      showExport={false}
      demo
    />
  );
}
