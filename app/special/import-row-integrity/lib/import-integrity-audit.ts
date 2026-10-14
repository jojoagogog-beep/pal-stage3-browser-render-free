export type VariantInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  sku: string | null;
  barcode: string | null;
  inventoryTracked: boolean;
  product: {
    id: string;
    legacyResourceId: string;
    title: string;
    handle: string;
  };
};

export type IssueKey =
  | "duplicate_sku"
  | "missing_identifier"
  | "missing_sku"
  | "suspicious_default_title"
  | "mixed_inventory_tracking";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type AuditedVariant = VariantInput & {
  issueKeys: IssueKey[];
  findings: string[];
  status: "No flagged pattern" | "Review row";
};

export type ProductAudit = VariantInput["product"] & {
  variants: AuditedVariant[];
  issueKeys: IssueKey[];
  affectedVariantCount: number;
  status: "No flagged pattern" | "Review import structure";
};

export type RankedIssue = IssueDefinition & {
  affectedProducts: number;
  affectedVariants: number;
};

export type AuditResult = {
  products: ProductAudit[];
  variants: AuditedVariant[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    productsWithIssues: number;
    variantsWithIssues: number;
    duplicateSkuGroups: number;
    rowsMissingIdentifiers: number;
    trackerMismatchProducts: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  duplicate_sku: {
    key: "duplicate_sku",
    label: "SKU appears on multiple variant rows",
    priority: "High",
    priorityRank: 100,
    recommendation:
      "Confirm whether the repeated SKU is intentional. Assign a stable, unique SKU to each affected variant when it is not.",
  },
  missing_identifier: {
    key: "missing_identifier",
    label: "Variant row has no SKU or barcode",
    priority: "High",
    priorityRank: 90,
    recommendation:
      "Add the merchant-assigned SKU or manufacturer barcode that belongs to this variant. Do not invent manufacturer identifiers.",
  },
  mixed_inventory_tracking: {
    key: "mixed_inventory_tracking",
    label: "Inventory tracking is mixed within a product",
    priority: "Medium",
    priorityRank: 80,
    recommendation:
      "Review the product's variants and confirm which rows should have inventory tracking enabled.",
  },
  missing_sku: {
    key: "missing_sku",
    label: "Variant row has a barcode but no SKU",
    priority: "Medium",
    priorityRank: 70,
    recommendation:
      "Add a stable internal SKU if the variant is managed by SKU. The existing barcode is left unchanged.",
  },
  suspicious_default_title: {
    key: "suspicious_default_title",
    label: "Default Title row needs review",
    priority: "Review",
    priorityRank: 50,
    recommendation:
      "Confirm that this is intentionally a single-variant product. If options were expected, review the source CSV option columns before importing again.",
  },
};

function clean(value: string | null | undefined) {
  return String(value ?? "").trim();
}

function skuKey(value: string | null) {
  return clean(value).toLocaleUpperCase();
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function auditCatalog(input: VariantInput[]): AuditResult {
  const variants = input.map((variant) => ({
    ...variant,
    issueKeys: [] as IssueKey[],
    findings: [] as string[],
    status: "No flagged pattern" as AuditedVariant["status"],
  }));

  const skuGroups = new Map<string, AuditedVariant[]>();
  for (const variant of variants) {
    const key = skuKey(variant.sku);
    if (!key) continue;
    const group = skuGroups.get(key) ?? [];
    group.push(variant);
    skuGroups.set(key, group);
  }

  const duplicateSkuGroups = [...skuGroups.values()].filter(
    (group) => group.length > 1,
  );
  for (const group of duplicateSkuGroups) {
    const sku = clean(group[0].sku);
    for (const variant of group) {
      variant.issueKeys.push("duplicate_sku");
      variant.findings.push(
        `SKU ${sku} appears on ${group.length} variant rows in this scan.`,
      );
    }
  }

  const variantsByProduct = new Map<string, AuditedVariant[]>();
  for (const variant of variants) {
    const productVariants = variantsByProduct.get(variant.product.id) ?? [];
    productVariants.push(variant);
    variantsByProduct.set(variant.product.id, productVariants);

    const sku = clean(variant.sku);
    const barcode = clean(variant.barcode);
    if (!sku && !barcode) {
      variant.issueKeys.push("missing_identifier");
      variant.findings.push("The variant has neither a SKU nor a barcode.");
    } else if (!sku) {
      variant.issueKeys.push("missing_sku");
      variant.findings.push("The variant has a barcode but its SKU is blank.");
    }

    const isDefaultTitle =
      clean(variant.title).toLocaleLowerCase() === "default title";
    const productIsDefaultTitle =
      clean(variant.product.title).toLocaleLowerCase() === "default title";
    if (isDefaultTitle && (productIsDefaultTitle || (!sku && !barcode))) {
      variant.issueKeys.push("suspicious_default_title");
      variant.findings.push(
        productIsDefaultTitle
          ? "The product and its variant both use Default Title."
          : "The Default Title variant also has no SKU or barcode.",
      );
    }
  }

  for (const productVariants of variantsByProduct.values()) {
    const trackedStates = unique(
      productVariants.map((variant) => variant.inventoryTracked),
    );
    if (trackedStates.length < 2) continue;
    for (const variant of productVariants) {
      variant.issueKeys.push("mixed_inventory_tracking");
      variant.findings.push(
        `Inventory tracking is ${variant.inventoryTracked ? "on" : "off"} for this row while sibling variants use a different setting.`,
      );
    }
  }

  for (const variant of variants) {
    variant.issueKeys = unique(variant.issueKeys);
    variant.findings = unique(variant.findings);
    variant.status = variant.issueKeys.length
      ? "Review row"
      : "No flagged pattern";
  }

  const products: ProductAudit[] = [...variantsByProduct.values()]
    .map((productVariants) => {
      const product = productVariants[0].product;
      const issueKeys = unique(
        productVariants.flatMap((variant) => variant.issueKeys),
      );
      return {
        ...product,
        variants: productVariants.sort(
          (a, b) =>
            b.issueKeys.length - a.issueKeys.length ||
            a.title.localeCompare(b.title),
        ),
        issueKeys,
        affectedVariantCount: productVariants.filter(
          (variant) => variant.issueKeys.length,
        ).length,
        status: (issueKeys.length
          ? "Review import structure"
          : "No flagged pattern") as ProductAudit["status"],
      };
    })
    .sort(
      (a, b) =>
        b.issueKeys.length - a.issueKeys.length ||
        b.affectedVariantCount - a.affectedVariantCount ||
        a.title.localeCompare(b.title),
    );

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => {
      const affectedVariants = variants.filter((variant) =>
        variant.issueKeys.includes(key),
      );
      return {
        ...ISSUE_DEFINITIONS[key],
        affectedVariants: affectedVariants.length,
        affectedProducts: new Set(
          affectedVariants.map((variant) => variant.product.id),
        ).size,
      };
    })
    .filter((issue) => issue.affectedVariants > 0)
    .sort(
      (a, b) =>
        b.priorityRank - a.priorityRank ||
        b.affectedVariants - a.affectedVariants ||
        a.label.localeCompare(b.label),
    );

  return {
    products,
    variants,
    rankedIssues,
    summary: {
      productsScanned: products.length,
      variantsScanned: variants.length,
      productsWithIssues: products.filter((product) => product.issueKeys.length)
        .length,
      variantsWithIssues: variants.filter((variant) => variant.issueKeys.length)
        .length,
      duplicateSkuGroups: duplicateSkuGroups.length,
      rowsMissingIdentifiers: variants.filter((variant) =>
        variant.issueKeys.includes("missing_identifier"),
      ).length,
      trackerMismatchProducts: products.filter((product) =>
        product.issueKeys.includes("mixed_inventory_tracking"),
      ).length,
    },
  };
}

function csvCell(value: string | number | boolean | null) {
  let text = String(value ?? "")
    .replaceAll("\r", " ")
    .replaceAll("\n", " ")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ");
  if (/^\s*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function productAdminUrl(shopDomain: string, productId: string) {
  const normalizedShop = shopDomain.trim().toLocaleLowerCase();
  if (!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(normalizedShop)) {
    throw new Error("Cannot create a product link for an invalid shop domain.");
  }
  return `https://${normalizedShop}/admin/products/${encodeURIComponent(productId)}`;
}

export function buildRemediationCsv(audit: AuditResult, shopDomain: string) {
  const rows: Array<Array<string | number | boolean | null>> = [
    [
      "Priority",
      "Finding",
      "Product",
      "Product handle",
      "Product admin link",
      "Variant",
      "Variant ID",
      "SKU",
      "Barcode",
      "Inventory tracked",
      "Evidence",
      "Recommended next step",
    ],
  ];

  for (const variant of audit.variants) {
    for (const key of variant.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      rows.push([
        issue.priority,
        issue.label,
        variant.product.title,
        variant.product.handle,
        productAdminUrl(shopDomain, variant.product.legacyResourceId),
        variant.title,
        variant.legacyResourceId,
        variant.sku,
        variant.barcode,
        variant.inventoryTracked,
        variant.findings.join(" "),
        issue.recommendation,
      ]);
    }
  }

  return `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}
