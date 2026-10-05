export type VariantInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  price: string;
  compareAtPrice: string | null;
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  variants: VariantInput[];
};

export type IssueKey =
  | "invalid_compare_at"
  | "partial_sale_mix"
  | "discount_spread"
  | "zero_price";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type ProductAudit = ProductInput & {
  issueKeys: IssueKey[];
  findings: string[];
  status: "Consistent" | "Review pricing";
  saleVariantCount: number;
  variantCount: number;
  discountRange: string;
};

export type RankedIssue = IssueDefinition & { affectedProducts: number };

export type AuditResult = {
  products: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    productsWithIssues: number;
    consistentProducts: number;
    invalidCompareAt: number;
    partialSaleMix: number;
    discountSpread: number;
    zeroPrice: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  invalid_compare_at: {
    key: "invalid_compare_at",
    label: "Compare-at price is not above selling price",
    priority: "High",
    priorityRank: 100,
    recommendation:
      "Review the affected variant and set compare-at above the selling price only when an intentional sale is active.",
  },
  partial_sale_mix: {
    key: "partial_sale_mix",
    label: "Sale state is mixed across variants",
    priority: "Medium",
    priorityRank: 80,
    recommendation:
      "Confirm whether only selected variants should be discounted before changing any price fields.",
  },
  discount_spread: {
    key: "discount_spread",
    label: "Discount rate varies sharply across variants",
    priority: "Review",
    priorityRank: 60,
    recommendation:
      "Review the discount percentages across variants and confirm the spread is intentional.",
  },
  zero_price: {
    key: "zero_price",
    label: "Variant has a zero selling price",
    priority: "Review",
    priorityRank: 50,
    recommendation:
      "Confirm zero-price variants are intentional and suitable for storefront sale.",
  },
};

function money(v: string | null) {
  const n = v == null ? NaN : Number(v);
  return Number.isFinite(n) ? n : NaN;
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const audited: ProductAudit[] = products.map((product) => {
    const issueKeys: IssueKey[] = [];
    const findings: string[] = [];
    const validSaleDiscounts: number[] = [];
    let saleVariantCount = 0;

    for (const variant of product.variants) {
      const price = money(variant.price);
      const compare = money(variant.compareAtPrice);

      if (Number.isFinite(price) && price === 0) {
        issueKeys.push("zero_price");
        findings.push(`${variant.title}: selling price is 0.`);
      }

      if (variant.compareAtPrice != null && Number.isFinite(compare)) {
        if (!Number.isFinite(price) || compare <= price) {
          issueKeys.push("invalid_compare_at");
          findings.push(
            `${variant.title}: compare-at ${variant.compareAtPrice} is not above price ${variant.price}.`,
          );
        } else {
          saleVariantCount += 1;
          validSaleDiscounts.push(((compare - price) / compare) * 100);
        }
      }
    }

    if (
      product.variants.length > 1 &&
      saleVariantCount > 0 &&
      saleVariantCount < product.variants.length
    ) {
      issueKeys.push("partial_sale_mix");
      findings.push(
        `${saleVariantCount} of ${product.variants.length} variants have a valid sale price while the others do not.`,
      );
    }

    if (validSaleDiscounts.length >= 2) {
      const min = Math.min(...validSaleDiscounts);
      const max = Math.max(...validSaleDiscounts);
      if (max - min >= 15) {
        issueKeys.push("discount_spread");
        findings.push(
          `Valid variant discounts range from ${min.toFixed(1)}% to ${max.toFixed(1)}%.`,
        );
      }
    }

    const range = validSaleDiscounts.length
      ? `${Math.min(...validSaleDiscounts).toFixed(1)}%–${Math.max(...validSaleDiscounts).toFixed(1)}%`
      : "No valid sale";

    return {
      ...product,
      issueKeys: unique(issueKeys),
      findings: unique(findings),
      status: issueKeys.length ? "Review pricing" : "Consistent",
      saleVariantCount,
      variantCount: product.variants.length,
      discountRange: range,
    };
  });

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => ({
      ...ISSUE_DEFINITIONS[key],
      affectedProducts: audited.filter((p) => p.issueKeys.includes(key)).length,
    }))
    .filter((x) => x.affectedProducts > 0)
    .sort((a, b) => b.priorityRank - a.priorityRank || b.affectedProducts - a.affectedProducts);

  return {
    products: audited.sort(
      (a, b) => b.issueKeys.length - a.issueKeys.length || a.title.localeCompare(b.title),
    ),
    rankedIssues,
    summary: {
      productsScanned: audited.length,
      variantsScanned: audited.reduce((n, p) => n + p.variants.length, 0),
      productsWithIssues: audited.filter((p) => p.issueKeys.length).length,
      consistentProducts: audited.filter((p) => !p.issueKeys.length).length,
      invalidCompareAt: audited.filter((p) => p.issueKeys.includes("invalid_compare_at")).length,
      partialSaleMix: audited.filter((p) => p.issueKeys.includes("partial_sale_mix")).length,
      discountSpread: audited.filter((p) => p.issueKeys.includes("discount_spread")).length,
      zeroPrice: audited.filter((p) => p.issueKeys.includes("zero_price")).length,
    },
  };
}

function csvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildRemediationCsv(audit: AuditResult) {
  const rows: Array<Array<string | number>> = [[
    "Priority","Issue","Product","Product admin link","Sale variants","Variants","Discount range","Finding","Recommended next step"
  ]];
  for (const p of audit.products) {
    for (const key of p.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      rows.push([
        issue.priority,
        issue.label,
        p.title,
        `shopify://admin/products/${p.legacyResourceId}`,
        p.saleVariantCount,
        p.variantCount,
        p.discountRange,
        p.findings.join(" "),
        issue.recommendation,
      ]);
    }
  }
  return "\uFEFF" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
