export type RuleInput = {
  column: string;
  relation: string;
  condition: string;
};

export type CollectionInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  handle: string;
  ruleSet: null | {
    appliedDisjunctively: boolean;
    rules: RuleInput[];
  };
};

export type AuditedCollection = CollectionInput & {
  mode: "Manual" | "ALL" | "ANY";
  ruleCount: number;
  duplicateRuleCount: number;
  duplicateRules: string[];
  needsReview: boolean;
};

export type AuditResult = {
  collections: AuditedCollection[];
  automated: AuditedCollection[];
  manual: AuditedCollection[];
  needsReview: AuditedCollection[];
  summary: {
    collectionsScanned: number;
    automatedCollections: number;
    manualCollections: number;
    anyMatchCollections: number;
    allMatchCollections: number;
    collectionsWithDuplicates: number;
  };
};

function signature(rule: RuleInput) {
  return [rule.column, rule.relation, rule.condition.trim().toLowerCase()].join("::");
}

export function auditCollections(collections: CollectionInput[]): AuditResult {
  const audited = collections.map((collection): AuditedCollection => {
    const rules = collection.ruleSet?.rules ?? [];
    const seen = new Map<string, number>();
    for (const rule of rules) {
      const key = signature(rule);
      seen.set(key, (seen.get(key) || 0) + 1);
    }
    const duplicateRules = [...seen.entries()]
      .filter(([, count]) => count > 1)
      .map(([key, count]) => key + " ×" + count);
    const automated = Boolean(collection.ruleSet);
    return {
      ...collection,
      mode: automated
        ? collection.ruleSet!.appliedDisjunctively ? "ANY" : "ALL"
        : "Manual",
      ruleCount: rules.length,
      duplicateRuleCount: duplicateRules.length,
      duplicateRules,
      needsReview: duplicateRules.length > 0,
    };
  });

  const automated = audited.filter((c) => c.mode !== "Manual");
  const manual = audited.filter((c) => c.mode === "Manual");
  const needsReview = audited.filter((c) => c.needsReview);

  return {
    collections: audited,
    automated,
    manual,
    needsReview,
    summary: {
      collectionsScanned: audited.length,
      automatedCollections: automated.length,
      manualCollections: manual.length,
      anyMatchCollections: automated.filter((c) => c.mode === "ANY").length,
      allMatchCollections: automated.filter((c) => c.mode === "ALL").length,
      collectionsWithDuplicates: needsReview.length,
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
    ["Collection", "Type", "Match mode", "Rule count",
      "Exact duplicate rules", "Admin link"],
    ...audit.collections.map((collection) => [
      collection.title,
      collection.mode === "Manual" ? "Manual" : "Automated",
      collection.mode,
      collection.ruleCount,
      collection.duplicateRules.join(" | ") || "None",
      collectionAdminUrl(shopDomain, collection.legacyResourceId),
    ]),
  ];
  return "\uFEFF" +
    rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
