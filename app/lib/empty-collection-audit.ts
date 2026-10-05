export type CollectionInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  handle: string;
  updatedAt: string;
  productsCount: number;
  countPrecision: string;
  ruleSet: null | {
    appliedDisjunctively: boolean;
    rules: Array<{ column: string; relation: string; condition: string }>;
  };
};

export type CollectionAudit = CollectionInput & {
  kind: "Manual" | "Automated";
  empty: boolean;
  ruleSummary: string;
};

export type AuditResult = {
  collections: CollectionAudit[];
  empty: CollectionAudit[];
  emptyManual: CollectionAudit[];
  emptyAutomated: CollectionAudit[];
  summary: {
    collectionsScanned: number;
    emptyCollections: number;
    emptyManual: number;
    emptyAutomated: number;
  };
};

export function auditCollections(collections: CollectionInput[]): AuditResult {
  const audited = collections.map((collection) => {
    const kind = collection.ruleSet ? "Automated" as const : "Manual" as const;
    const ruleSummary = collection.ruleSet
      ? collection.ruleSet.rules.map((rule) => rule.column + " " + rule.relation + " " + rule.condition).join(" · ")
      : "Manual product selection";
    return { ...collection, kind, empty: collection.productsCount === 0, ruleSummary };
  });
  const empty = audited.filter((c) => c.empty);
  const emptyManual = empty.filter((c) => c.kind === "Manual");
  const emptyAutomated = empty.filter((c) => c.kind === "Automated");
  return {
    collections: audited,
    empty,
    emptyManual,
    emptyAutomated,
    summary: {
      collectionsScanned: audited.length,
      emptyCollections: empty.length,
      emptyManual: emptyManual.length,
      emptyAutomated: emptyAutomated.length,
    },
  };
}

function csvCell(value: string | number) {
  const s = String(value ?? "");
  return '"' + s.replaceAll('"', '""') + '"';
}

export function collectionAdminUrl(shopDomain: string, legacyResourceId: string) {
  const store = shopDomain.replace(/\.myshopify\.com$/i, "");
  return "https://admin.shopify.com/store/" + encodeURIComponent(store) + "/collections/" + encodeURIComponent(legacyResourceId);
}

export function buildDiagnosticCsv(audit: AuditResult, shopDomain: string) {
  const rows = [
    ["Collection", "Type", "Product count", "Rule summary", "Updated at", "Admin link"],
    ...audit.collections.map((collection) => [
      collection.title,
      collection.kind,
      collection.productsCount,
      collection.ruleSummary,
      collection.updatedAt,
      collectionAdminUrl(shopDomain, collection.legacyResourceId),
    ]),
  ];
  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
