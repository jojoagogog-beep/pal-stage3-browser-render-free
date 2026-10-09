export type WeightValue = { value: number; unit: string };

export type VariantInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  requiresShipping: boolean;
  tracked: boolean;
  weight: WeightValue | null;
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  variants: VariantInput[];
};

export type IssueKey =
  | "mixed_shipping_requirement"
  | "physical_missing_weight"
  | "mixed_inventory_tracking";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type VariantAudit = VariantInput & { grams: number | null; issueKeys: IssueKey[] };
export type ProductAudit = Omit<ProductInput, "variants"> & {
  variants: VariantAudit[];
  issueKeys: IssueKey[];
  findings: string[];
  status: "Consistent" | "Review";
};
export type RankedIssue = IssueDefinition & { affectedProducts: number; affectedVariants: number };
export type AuditResult = {
  products: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    productsWithIssues: number;
    mixedShippingProducts: number;
    missingWeightVariants: number;
    mixedTrackingProducts: number;
    consistentProducts: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  mixed_shipping_requirement: {
    key: "mixed_shipping_requirement",
    label: "Sibling variants mix shipping-required states",
    priority: "High",
    priorityRank: 100,
    recommendation: "Review whether each variant is intentionally physical or non-physical before editing shipping behavior.",
  },
  physical_missing_weight: {
    key: "physical_missing_weight",
    label: "Physical-shipping variant has missing or zero weight",
    priority: "Medium",
    priorityRank: 85,
    recommendation: "Confirm the variant's weight before relying on weight-sensitive fulfillment or shipping rules.",
  },
  mixed_inventory_tracking: {
    key: "mixed_inventory_tracking",
    label: "Sibling variants mix tracked and untracked inventory",
    priority: "Review",
    priorityRank: 65,
    recommendation: "Confirm that tracked versus untracked inventory is intentional for each sibling variant.",
  },
};

function unique<T>(values: T[]) { return [...new Set(values)]; }
function toGrams(weight: WeightValue | null): number | null {
  if (!weight) return null;
  const v = Number(weight.value);
  if (!Number.isFinite(v)) return null;
  switch (String(weight.unit).toUpperCase()) {
    case "GRAMS": return v;
    case "KILOGRAMS": return v * 1000;
    case "OUNCES": return v * 28.349523125;
    case "POUNDS": return v * 453.59237;
    default: return null;
  }
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const audited: ProductAudit[] = products.map((product) => {
    const variants: VariantAudit[] = product.variants.map((variant) => {
      const grams = toGrams(variant.weight);
      const issueKeys: IssueKey[] = [];
      if (variant.requiresShipping && (grams == null || grams <= 0)) issueKeys.push("physical_missing_weight");
      return { ...variant, grams, issueKeys };
    });

    const shippingStates = new Set(variants.map((v) => v.requiresShipping));
    const trackingStates = new Set(variants.map((v) => v.tracked));
    const issueKeys: IssueKey[] = [];
    const findings: string[] = [];

    if (variants.length > 1 && shippingStates.size > 1) {
      issueKeys.push("mixed_shipping_requirement");
      const physical = variants.filter((v) => v.requiresShipping).length;
      findings.push(`${physical} physical and ${variants.length - physical} non-physical sibling variant(s).`);
    }
    if (variants.some((v) => v.issueKeys.includes("physical_missing_weight"))) {
      issueKeys.push("physical_missing_weight");
      const count = variants.filter((v) => v.issueKeys.includes("physical_missing_weight")).length;
      findings.push(`${count} physical-shipping variant(s) have missing or zero weight.`);
    }
    if (variants.length > 1 && trackingStates.size > 1) {
      issueKeys.push("mixed_inventory_tracking");
      const tracked = variants.filter((v) => v.tracked).length;
      findings.push(`${tracked} tracked and ${variants.length - tracked} untracked sibling variant(s).`);
    }

    for (const v of variants) {
      if (issueKeys.includes("mixed_shipping_requirement") && variants.length > 1) v.issueKeys.push("mixed_shipping_requirement");
      if (issueKeys.includes("mixed_inventory_tracking") && variants.length > 1) v.issueKeys.push("mixed_inventory_tracking");
      v.issueKeys = unique(v.issueKeys);
    }

    return {
      ...product,
      variants,
      issueKeys: unique(issueKeys),
      findings: unique(findings),
      status: issueKeys.length ? "Review" : "Consistent",
    };
  });

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => {
      const affected = audited.filter((p) => p.issueKeys.includes(key));
      return {
        ...ISSUE_DEFINITIONS[key],
        affectedProducts: affected.length,
        affectedVariants: affected.reduce((n, p) => n + p.variants.filter((v) => v.issueKeys.includes(key)).length, 0),
      };
    })
    .filter((x) => x.affectedProducts > 0)
    .sort((a, b) => b.priorityRank - a.priorityRank || b.affectedProducts - a.affectedProducts);

  const sortedProducts = [...audited].sort((a, b) => b.issueKeys.length - a.issueKeys.length || a.title.localeCompare(b.title));
  return {
    products: sortedProducts,
    rankedIssues,
    summary: {
      productsScanned: sortedProducts.length,
      variantsScanned: sortedProducts.reduce((n, p) => n + p.variants.length, 0),
      productsWithIssues: sortedProducts.filter((p) => p.issueKeys.length > 0).length,
      mixedShippingProducts: sortedProducts.filter((p) => p.issueKeys.includes("mixed_shipping_requirement")).length,
      missingWeightVariants: sortedProducts.reduce((n, p) => n + p.variants.filter((v) => v.issueKeys.includes("physical_missing_weight")).length, 0),
      mixedTrackingProducts: sortedProducts.filter((p) => p.issueKeys.includes("mixed_inventory_tracking")).length,
      consistentProducts: sortedProducts.filter((p) => p.issueKeys.length === 0).length,
    },
  };
}

function csvCell(value: string | number | boolean | null) {
  let text = value == null ? "" : String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildRemediationCsv(audit: AuditResult) {
  const rows: Array<Array<string | number | boolean | null>> = [[
    "Priority", "Finding", "Product", "Product admin link", "Variant", "Requires shipping", "Inventory tracked", "Weight", "Unit", "Recommended next step"
  ]];
  for (const product of audit.products) {
    for (const key of product.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      if (key === "physical_missing_weight") {
        for (const variant of product.variants.filter((v) => v.issueKeys.includes(key))) {
          rows.push([issue.priority, issue.label, product.title, `shopify://admin/products/${product.legacyResourceId}`, variant.title, variant.requiresShipping, variant.tracked, variant.weight?.value ?? "", variant.weight?.unit ?? "", issue.recommendation]);
        }
      } else {
        rows.push([issue.priority, issue.label, product.title, `shopify://admin/products/${product.legacyResourceId}`, "", "", "", "", "", issue.recommendation]);
      }
    }
  }
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
