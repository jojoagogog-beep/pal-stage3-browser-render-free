import { useSearchParams } from "react-router";
import { FeedDashboard } from "./components/feed-dashboard";
import { auditCatalog } from "./lib/feed-audit";
import {
  demoProducts,
  demoVariants,
  readyDemoCatalog,
} from "./lib/demo-catalog";

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "issues";
  const source =
    state === "ready"
      ? readyDemoCatalog()
      : { products: demoProducts, variants: demoVariants };
  const audit = auditCatalog(source.products, source.variants);

  return (
    <FeedDashboard
      audit={audit}
      shopName="PAL Demo Store"
      scannedAt="Sep 30, 2026, 02:30 PM UTC"
      coverageLimited={state === "limit"}
      showExport={false}
      demo
    />
  );
}
