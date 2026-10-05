export type CollectionInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  handle: string;
  sortOrder: string;
};

export type AuditedCollection = CollectionInput & {
  manualSort: boolean;
};

export type AuditResult = {
  collections: AuditedCollection[];
  manual: AuditedCollection[];
  automatic: AuditedCollection[];
  counts: Record<string, number>;
  summary: {
    collectionsScanned: number;
    manualSortCollections: number;
    automaticSortCollections: number;
    sortModesUsed: number;
  };
};

export function auditCollections(collections: CollectionInput[]): AuditResult {
  const audited = collections.map((collection) => ({
    ...collection,
    manualSort: collection.sortOrder === "MANUAL",
  }));
  const manual = audited.filter((c) => c.manualSort);
  const automatic = audited.filter((c) => !c.manualSort);
  const counts: Record<string, number> = {};
  for (const collection of audited) {
    counts[collection.sortOrder] = (counts[collection.sortOrder] || 0) + 1;
  }

  return {
    collections: audited,
    manual,
    automatic,
    counts,
    summary: {
      collectionsScanned: audited.length,
      manualSortCollections: manual.length,
      automaticSortCollections: automatic.length,
      sortModesUsed: Object.keys(counts).length,
    },
  };
}

function csvCell(value: string | number) {
  const s = String(value ?? "");
  return '"' + s.replaceAll('"', '""') + '"';
}
export function collectionAdminUrl(shopDomain: string, legacyResourceId: string) {
  const store = shopDomain.replace(/\.myshopify\.com$/i, "");
  return "https://admin.shopify.com/store/" +
    encodeURIComponent(store) + "/collections/" +
    encodeURIComponent(legacyResourceId);
}

export function buildDiagnosticCsv(audit: AuditResult, shopDomain: string) {
  const rows = [
    ["Collection", "Sort order", "Manual sort", "Admin link"],
    ...audit.collections.map((collection) => [
      collection.title,
      collection.sortOrder,
      collection.manualSort ? "Yes" : "No",
      collectionAdminUrl(shopDomain, collection.legacyResourceId),
    ]),
  ];
  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
