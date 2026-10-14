export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  vendor: string;
  tags: string[];
  categoryName: string | null;
  hasImage: boolean;
};

export type VariantInput = {
  id: string;
  productId: string;
  title: string;
  sku: string | null;
  barcode: string | null;
};

export type ProductKind = "standard" | "custom" | "unclassified";
export type IssueKey =
  | "missing_title"
  | "missing_vendor"
  | "missing_category"
  | "missing_image"
  | "missing_sku"
  | "missing_gtin"
  | "review_custom_identifier"
  | "review_unclassified_identifier";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  channel: string;
  recommendation: string;
};

export type ProductAudit = ProductInput & {
  kind: ProductKind;
  kindLabel: string;
  variants: VariantInput[];
  issueKeys: IssueKey[];
  actionIssueCount: number;
  identifierReview: boolean;
  status: "Ready" | "Action needed" | "Review identifiers";
};

export type RankedIssue = IssueDefinition & {
  affectedProducts: number;
  affectedVariants: number;
};

export type AuditResult = {
  products: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    productsReady: number;
    productsWithActions: number;
    productsForIdentifierReview: number;
    highPriorityFindings: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  missing_image: {
    key: "missing_image",
    label: "Missing product image",
    priority: "High",
    priorityRank: 100,
    channel: "Google and Meta",
    recommendation: "Add a clear primary product image in the product record.",
  },
  missing_title: {
    key: "missing_title",
    label: "Missing product title",
    priority: "High",
    priorityRank: 95,
    channel: "Google and Meta",
    recommendation: "Add a specific product title in the product record.",
  },
  missing_vendor: {
    key: "missing_vendor",
    label: "Missing brand or vendor",
    priority: "High",
    priorityRank: 90,
    channel: "Google and Meta",
    recommendation:
      "Add the product brand in the vendor field, or classify the item if it is custom-made.",
  },
  missing_category: {
    key: "missing_category",
    label: "Missing product category",
    priority: "High",
    priorityRank: 85,
    channel: "Google and Meta",
    recommendation:
      "Assign the most specific applicable product category.",
  },
  missing_gtin: {
    key: "missing_gtin",
    label: "Missing GTIN/barcode on standard products",
    priority: "High",
    priorityRank: 80,
    channel: "Google identifiers",
    recommendation:
      "Add the manufacturer-assigned GTIN when the product has one; do not invent identifiers.",
  },
  missing_sku: {
    key: "missing_sku",
    label: "Missing variant SKU",
    priority: "Medium",
    priorityRank: 60,
    channel: "Catalog operations",
    recommendation: "Add a stable internal SKU for each affected variant.",
  },
  review_unclassified_identifier: {
    key: "review_unclassified_identifier",
    label: "Identifier type needs classification",
    priority: "Review",
    priorityRank: 45,
    channel: "Google identifiers",
    recommendation:
      "Confirm whether the product is branded, custom, handmade, or print-on-demand before deciding whether a GTIN is expected.",
  },
  review_custom_identifier: {
    key: "review_custom_identifier",
    label: "Review identifiers for likely custom/POD items",
    priority: "Review",
    priorityRank: 40,
    channel: "Google identifiers",
    recommendation:
      "Review channel identifier rules for this likely custom or print-on-demand item; do not create a GTIN.",
  },
};

const CUSTOM_CUES = [
  "custom",
  "customized",
  "handmade",
  "made-to-order",
  "made to order",
  "personalized",
  "personalised",
  "pod",
  "print-on-demand",
  "print on demand",
];

function normalize(value: string | null | undefined) {
  return String(value ?? "")
    .trim()
    .toLocaleLowerCase();
}

function classifyProduct(product: ProductInput): ProductKind {
  const searchable = [product.title, ...product.tags].map(normalize);
  if (
    searchable.some((value) => CUSTOM_CUES.some((cue) => value.includes(cue)))
  ) {
    return "custom";
  }
  return normalize(product.vendor) ? "standard" : "unclassified";
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function auditCatalog(
  products: ProductInput[],
  variants: VariantInput[],
): AuditResult {
  const variantsByProduct = new Map<string, VariantInput[]>();
  for (const variant of variants) {
    const current = variantsByProduct.get(variant.productId) ?? [];
    current.push(variant);
    variantsByProduct.set(variant.productId, current);
  }

  const auditedProducts: ProductAudit[] = products.map((product) => {
    const productVariants = variantsByProduct.get(product.id) ?? [];
    const kind = classifyProduct(product);
    const missingBarcode = productVariants.some(
      (variant) => !normalize(variant.barcode),
    );
    const issueKeys: IssueKey[] = [];

    if (!normalize(product.title)) issueKeys.push("missing_title");
    if (!normalize(product.vendor)) issueKeys.push("missing_vendor");
    if (!normalize(product.categoryName)) issueKeys.push("missing_category");
    if (!product.hasImage) issueKeys.push("missing_image");
    if (productVariants.some((variant) => !normalize(variant.sku)))
      issueKeys.push("missing_sku");
    if (missingBarcode && kind === "standard") issueKeys.push("missing_gtin");
    if (missingBarcode && kind === "custom")
      issueKeys.push("review_custom_identifier");
    if (missingBarcode && kind === "unclassified")
      issueKeys.push("review_unclassified_identifier");

    const dedupedIssues = unique(issueKeys);
    const identifierReview = dedupedIssues.some((key) =>
      key.startsWith("review_"),
    );
    const actionIssueCount = dedupedIssues.filter(
      (key) => !key.startsWith("review_"),
    ).length;

    return {
      ...product,
      kind,
      kindLabel:
        kind === "custom"
          ? "Likely custom/POD"
          : kind === "standard"
            ? "Standard branded"
            : "Needs classification",
      variants: productVariants,
      issueKeys: dedupedIssues,
      actionIssueCount,
      identifierReview,
      status:
        actionIssueCount > 0
          ? "Action needed"
          : identifierReview
            ? "Review identifiers"
            : "Ready",
    };
  });

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => {
      const affected = auditedProducts.filter((product) =>
        product.issueKeys.includes(key),
      );
      const isVariantIssue = [
        "missing_sku",
        "missing_gtin",
        "review_custom_identifier",
        "review_unclassified_identifier",
      ].includes(key);
      const affectedVariants = isVariantIssue
        ? affected.reduce((total, product) => {
            const missing = product.variants.filter((variant) =>
              key === "missing_sku"
                ? !normalize(variant.sku)
                : !normalize(variant.barcode),
            ).length;
            return total + missing;
          }, 0)
        : 0;
      return {
        ...ISSUE_DEFINITIONS[key],
        affectedProducts: affected.length,
        affectedVariants,
      };
    })
    .filter((issue) => issue.affectedProducts > 0)
    .sort(
      (a, b) =>
        b.priorityRank - a.priorityRank ||
        b.affectedProducts - a.affectedProducts ||
        a.label.localeCompare(b.label),
    );

  return {
    products: auditedProducts.sort(
      (a, b) =>
        b.actionIssueCount - a.actionIssueCount ||
        Number(b.identifierReview) - Number(a.identifierReview) ||
        a.title.localeCompare(b.title),
    ),
    rankedIssues,
    summary: {
      productsScanned: auditedProducts.length,
      variantsScanned: variants.length,
      productsReady: auditedProducts.filter(
        (product) => product.status === "Ready",
      ).length,
      productsWithActions: auditedProducts.filter(
        (product) => product.actionIssueCount > 0,
      ).length,
      productsForIdentifierReview: auditedProducts.filter(
        (product) => product.identifierReview,
      ).length,
      highPriorityFindings: rankedIssues
        .filter((issue) => issue.priority === "High")
        .reduce((total, issue) => total + issue.affectedProducts, 0),
    },
  };
}

function protectCsvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildRemediationCsv(audit: AuditResult) {
  const header = [
    "Priority",
    "Issue",
    "Channel relevance",
    "Product",
    "Product admin link",
    "Product classification",
    "Variant",
    "SKU",
    "Barcode / GTIN",
    "Recommended next step",
  ];
  const rows: Array<Array<string | number>> = [header];

  for (const product of audit.products) {
    for (const key of product.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      const isVariantIssue = [
        "missing_sku",
        "missing_gtin",
        "review_custom_identifier",
        "review_unclassified_identifier",
      ].includes(key);
      const affectedVariants = isVariantIssue
        ? product.variants.filter((variant) =>
            key === "missing_sku"
              ? !normalize(variant.sku)
              : !normalize(variant.barcode),
          )
        : [null];

      for (const variant of affectedVariants) {
        rows.push([
          issue.priority,
          issue.label,
          issue.channel,
          product.title,
          `shopify://admin/products/${product.legacyResourceId}`,
          product.kindLabel,
          variant?.title ?? "",
          variant?.sku ?? "",
          variant?.barcode ?? "",
          issue.recommendation,
        ]);
      }
    }
  }

  return `\uFEFF${rows.map((row) => row.map(protectCsvCell).join(",")).join("\r\n")}\r\n`;
}
