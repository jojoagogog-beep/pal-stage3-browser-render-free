import { useSearchParams } from "react-router";
import { ImportIntegrityDashboard } from "./components/import-integrity-dashboard";
import { auditCatalog } from "./lib/import-integrity-audit";
import { demoCatalogFor } from "./lib/demo-catalog";

export default function ReviewDemo() {
  const [params] = useSearchParams();
  const state = params.get("state") || "overview";
  return (
    <ImportIntegrityDashboard
      audit={auditCatalog(demoCatalogFor(state))}
      shopName="PAL Demo Store"
      scannedAt="Sep 30, 2026, 09:30 AM UTC"
      coverageLimited={state === "limit"}
      showExport={false}
      demo
    />
  );
}
