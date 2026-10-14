import { useSearchParams } from "react-router";
import { VariantDashboard } from "./components/variant-dashboard";
import { auditCatalog } from "./lib/variant-order-audit";
import { demoProducts, readyDemoCatalog } from "./lib/demo-catalog";

function sourceFor(state: string) {
  if (state === "ready") return readyDemoCatalog();
  if (state === "order") {
    return demoProducts.filter((p) =>
      ["1001", "1002", "1005", "1006"].includes(p.legacyResourceId),
    );
  }
  if (state === "naming") {
    return demoProducts.filter((p) =>
      ["1001", "1003"].includes(p.legacyResourceId),
    );
  }
  if (state === "numeric") {
    return demoProducts.filter((p) => p.legacyResourceId === "1004");
  }
  return demoProducts;
}

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "issues";
  return (
    <VariantDashboard
      audit={auditCatalog(sourceFor(state))}
      shopName="PAL Demo Store"
      scannedAt="Sep 30, 2026, 08:30 AM UTC"
      coverageLimited={state === "limit"}
      showExport={false}
      demo
    />
  );
}
