export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  status: string;
  collections: Array<{ id: string; title: string; handle: string }>;
  collectionsLimited?: boolean;
};

export type ProductAudit = ProductInput & {
  collectionCountObserved: number;
  statusLabel: "Orphaned" | "In collection";
};

export type AuditResult = {
  products: ProductAudit[];
  orphaned: ProductAudit[];
  activeOrphaned: ProductAudit[];
  nonActiveOrphaned: ProductAudit[];
  summary: {
    productsScanned: number;
    orphanedProducts: number;
    activeOrphanedProducts: number;
    coveredProducts: number;
  };
};

export function auditCatalog(products: ProductInput[]): AuditResult {
  const audited = products.map((product) => ({
    ...product,
    collectionCountObserved: product.collections.length,
    statusLabel: product.collections.length === 0 ? "Orphaned" as const : "In collection" as const,
  }));
  const orphaned = audited.filter((p) => p.statusLabel === "Orphaned");
  const activeOrphaned = orphaned.filter((p) => p.status === "ACTIVE");
  const nonActiveOrphaned = orphaned.filter((p) => p.status !== "ACTIVE");
  return {
    products: audited,
    orphaned,
    activeOrphaned,
    nonActiveOrphaned,
    summary: {
      productsScanned: audited.length,
      orphanedProducts: orphaned.length,
      activeOrphanedProducts: activeOrphaned.length,
      coveredProducts: audited.length - orphaned.length,
    },
  };
}

function csvCell(value: string | number) {
  const s = String(value ?? "");
  return '"' + s.replaceAll('"', '""') + '"';
}

export function productAdminUrl(shopDomain: string, legacyResourceId: string) {
  const store = shopDomain.replace(/\.myshopify\.com$/i, "");
  return "https://admin.shopify.com/store/" + encodeURIComponent(store) + "/products/" + encodeURIComponent(legacyResourceId);
}

export function buildDiagnosticCsv(audit: AuditResult, shopDomain: string) {
  const rows = [
    ["Product", "Product status", "Collection status", "Observed collections", "Admin link"],
    ...audit.products.map((product) => [
      product.title,
      product.status,
      product.statusLabel,
      product.collections.map((c) => c.title).join(" | "),
      productAdminUrl(shopDomain, product.legacyResourceId),
    ]),
  ];
  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
