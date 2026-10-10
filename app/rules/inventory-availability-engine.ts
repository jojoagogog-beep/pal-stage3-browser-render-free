export type InventoryLevelInput = {
  available: number;
};

export type VariantInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  inventoryPolicy: "CONTINUE" | "DENY";
  inventoryQuantity: number;
  tracked: boolean;
  inventoryLevels: InventoryLevelInput[];
  inventoryLevelsLimited?: boolean;
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  status: "ACTIVE" | "DRAFT" | "ARCHIVED" | string;
  variants: VariantInput[];
  variantsLimited?: boolean;
};

export type IssueKey =
  | "mixed_tracking"
  | "mixed_inventory_policy"
  | "tracked_without_location"
  | "untracked_with_location_records"
  | "aggregate_availability_mismatch"
  | "stocked_inactive_product";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type VariantAudit = VariantInput & {
  issueKeys: IssueKey[];
  availableAcrossLevels: number;
  status: "Aligned" | "Untracked" | "Review";
};

export type ProductAudit = Omit<ProductInput, "variants"> & {
  variants: VariantAudit[];
  issueKeys: IssueKey[];
  findings: string[];
  trackedCount: number;
  untrackedCount: number;
  variantsWithIssues: number;
  statusLabel: "No mismatch found" | "Review signals";
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
    productsWithIssues: number;
    variantsWithIssues: number;
    mixedTrackingProducts: number;
    locationReviewVariants: number;
    productsWithoutMismatch: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  tracked_without_location: {
    key: "tracked_without_location",
    label: "Tracked variant has no inventory location record",
    priority: "High",
    priorityRank: 100,
    recommendation:
      "Review the variant's inventory locations and confirm it is stocked at an intended fulfillment location.",
  },
  aggregate_availability_mismatch: {
    key: "aggregate_availability_mismatch",
    label: "Aggregate and location availability disagree",
    priority: "High",
    priorityRank: 95,
    recommendation:
      "Review the variant's inventory levels and location assignments for an unexpected availability difference.",
  },
  mixed_tracking: {
    key: "mixed_tracking",
    label: "Sibling variants mix tracked and untracked inventory",
    priority: "Medium",
    priorityRank: 80,
    recommendation:
      "Confirm whether every sibling variant should follow the same inventory-tracking approach.",
  },
  mixed_inventory_policy: {
    key: "mixed_inventory_policy",
    label: "Sibling variants use different out-of-stock policies",
    priority: "Medium",
    priorityRank: 75,
    recommendation:
      "Confirm which variants should stop selling at zero and which should continue selling.",
  },
  untracked_with_location_records: {
    key: "untracked_with_location_records",
    label: "Untracked variant still has location inventory records",
    priority: "Review",
    priorityRank: 60,
    recommendation:
      "Confirm that inventory tracking is intentionally disabled and review leftover location records if availability is unexpected.",
  },
  stocked_inactive_product: {
    key: "stocked_inactive_product",
    label: "Stocked product is not active",
    priority: "Review",
    priorityRank: 50,
    recommendation:
      "Confirm the product status is intentional before reviewing its sales-channel publication settings.",
  },
};

const PRODUCT_LEVEL_ISSUES = new Set<IssueKey>([
  "mixed_tracking",
  "mixed_inventory_policy",
  "stocked_inactive_product",
]);

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const auditedProducts: ProductAudit[] = products.map((product) => {
    const findings: string[] = [];
    const productIssueKeys: IssueKey[] = [];
    const trackedCount = product.variants.filter((variant) => variant.tracked).length;
    const untrackedCount = product.variants.length - trackedCount;

    if (trackedCount > 0 && untrackedCount > 0) {
      productIssueKeys.push("mixed_tracking");
      findings.push(
        `${trackedCount} tracked and ${untrackedCount} untracked sibling variants.`,
      );
    }

    const policyCount = new Set(
      product.variants.map((variant) => variant.inventoryPolicy),
    ).size;
    if (policyCount > 1) {
      productIssueKeys.push("mixed_inventory_policy");
      findings.push("Sibling variants use both stop-selling and continue-selling policies.");
    }

    if (
      product.status !== "ACTIVE" &&
      product.variants.some((variant) => variant.inventoryQuantity > 0)
    ) {
      productIssueKeys.push("stocked_inactive_product");
      findings.push(
        `${product.status.toLocaleLowerCase()} product has positive aggregate inventory.`,
      );
    }

    const variants: VariantAudit[] = product.variants.map((variant) => {
      const issueKeys: IssueKey[] = [];
      const availableAcrossLevels = variant.inventoryLevels.reduce(
        (total, level) => total + level.available,
        0,
      );

      if (variant.tracked && variant.inventoryLevels.length === 0) {
        issueKeys.push("tracked_without_location");
        findings.push(`${variant.title}: tracking is on but no location record was returned.`);
      }

      if (!variant.tracked && variant.inventoryLevels.length > 0) {
        issueKeys.push("untracked_with_location_records");
        findings.push(
          `${variant.title}: tracking is off while ${variant.inventoryLevels.length} location record${
            variant.inventoryLevels.length === 1 ? " remains" : "s remain"
          }.`,
        );
      }

      if (
        variant.tracked &&
        !variant.inventoryLevelsLimited &&
        variant.inventoryLevels.length > 0 &&
        variant.inventoryQuantity !== availableAcrossLevels
      ) {
        issueKeys.push("aggregate_availability_mismatch");
        findings.push(
          `${variant.title}: aggregate quantity is ${variant.inventoryQuantity}, while checked location availability totals ${availableAcrossLevels}.`,
        );
      }

      return {
        ...variant,
        issueKeys,
        availableAcrossLevels,
        status: issueKeys.length
          ? "Review"
          : variant.tracked
            ? "Aligned"
            : "Untracked",
      };
    });

    const issueKeys = unique([
      ...productIssueKeys,
      ...variants.flatMap((variant) => variant.issueKeys),
    ]);
    const variantsWithIssues = variants.filter(
      (variant) => variant.issueKeys.length > 0,
    ).length;

    return {
      ...product,
      variants,
      issueKeys,
      findings: unique(findings),
      trackedCount,
      untrackedCount,
      variantsWithIssues,
      statusLabel: issueKeys.length ? "Review signals" : "No mismatch found",
    };
  });

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => {
      const affectedProducts = auditedProducts.filter((product) =>
        product.issueKeys.includes(key),
      );
      const affectedVariants = PRODUCT_LEVEL_ISSUES.has(key)
        ? 0
        : affectedProducts.reduce(
            (total, product) =>
              total +
              product.variants.filter((variant) =>
                variant.issueKeys.includes(key),
              ).length,
            0,
          );
      return {
        ...ISSUE_DEFINITIONS[key],
        affectedProducts: affectedProducts.length,
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

  const sortedProducts = auditedProducts.sort(
    (a, b) =>
      b.issueKeys.length - a.issueKeys.length || a.title.localeCompare(b.title),
  );

  return {
    products: sortedProducts,
    rankedIssues,
    summary: {
      productsScanned: sortedProducts.length,
      variantsScanned: sortedProducts.reduce(
        (total, product) => total + product.variants.length,
        0,
      ),
      productsWithIssues: sortedProducts.filter((product) => product.issueKeys.length)
        .length,
      variantsWithIssues: sortedProducts.reduce(
        (total, product) => total + product.variantsWithIssues,
        0,
      ),
      mixedTrackingProducts: sortedProducts.filter((product) =>
        product.issueKeys.includes("mixed_tracking"),
      ).length,
      locationReviewVariants: sortedProducts.reduce(
        (total, product) =>
          total +
          product.variants.filter((variant) =>
            variant.issueKeys.some((key) =>
              [
                "tracked_without_location",
                "untracked_with_location_records",
                "aggregate_availability_mismatch",
              ].includes(key),
            ),
          ).length,
        0,
      ),
      productsWithoutMismatch: sortedProducts.filter(
        (product) => !product.issueKeys.length,
      ).length,
    },
  };
}

function csvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildDiagnosticCsv(audit: AuditResult) {
  const rows: Array<Array<string | number>> = [
    [
      "Priority",
      "Finding",
      "Product",
      "Product status",
      "Product admin link",
      "Variant",
      "Inventory tracked",
      "Out-of-stock policy",
      "Aggregate quantity",
      "Checked location availability",
      "Recommended next step",
    ],
  ];

  for (const product of audit.products) {
    for (const key of product.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      const affectedVariants = PRODUCT_LEVEL_ISSUES.has(key)
        ? [null]
        : product.variants.filter((variant) => variant.issueKeys.includes(key));

      for (const variant of affectedVariants) {
        rows.push([
          issue.priority,
          issue.label,
          product.title,
          product.status,
          `shopify://admin/products/${product.legacyResourceId}`,
          variant?.title ?? "",
          variant ? (variant.tracked ? "Yes" : "No") : "",
          variant?.inventoryPolicy ?? "",
          variant?.inventoryQuantity ?? "",
          variant?.availableAcrossLevels ?? "",
          issue.recommendation,
        ]);
      }
    }
  }

  return `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}
