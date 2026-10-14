export type ProductOptionInput = {
  name: string;
  position: number;
  values: string[];
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  options: ProductOptionInput[];
};

export type IssueKey =
  | "sequence_mismatch"
  | "name_drift"
  | "numeric_value_order"
  | "duplicate_option_family";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type ProductAudit = ProductInput & {
  displaySequence: string;
  normalizedSequence: string[];
  issueKeys: IssueKey[];
  findings: string[];
  status: "Consistent" | "Review structure";
};

export type RankedIssue = IssueDefinition & {
  affectedProducts: number;
};

export type AuditResult = {
  products: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    optionsScanned: number;
    productsWithIssues: number;
    consistentProducts: number;
    sequenceIssues: number;
    namingDriftIssues: number;
    numericOrderReviews: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  sequence_mismatch: {
    key: "sequence_mismatch",
    label: "Option sequence differs across comparable products",
    priority: "High",
    priorityRank: 100,
    recommendation:
      "Review the product option order in Shopify Admin and standardize the intended sequence.",
  },
  name_drift: {
    key: "name_drift",
    label: "Option family uses inconsistent labels",
    priority: "Medium",
    priorityRank: 80,
    recommendation:
      "Standardize option labels used for the same concept, such as Color versus Colour.",
  },
  duplicate_option_family: {
    key: "duplicate_option_family",
    label: "Product contains duplicate option families",
    priority: "Medium",
    priorityRank: 70,
    recommendation:
      "Review duplicate or near-duplicate option names on the product before editing variants.",
  },
  numeric_value_order: {
    key: "numeric_value_order",
    label: "Numeric option values appear out of order",
    priority: "Review",
    priorityRank: 50,
    recommendation:
      "Confirm the intended display order for numeric option values before making changes.",
  },
};

const ALIASES: Record<string, string> = {
  colors: "color",
  colour: "color",
  colours: "color",
  sizes: "size",
  widths: "width",
  lengths: "length",
  materials: "material",
  styles: "style",
};

function rawKey(value: string) {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

export function canonicalOptionName(value: string) {
  const normalized = rawKey(value)
    .replace(/[\-_]+/g, " ")
    .replace(/[^a-z0-9 ]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return ALIASES[normalized] ?? normalized;
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

function strictMode(values: string[]): string | null {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  const ranked = [...counts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  if (ranked.length === 0) return null;
  if (ranked.length === 1) return ranked[0][0];
  return ranked[0][1] > ranked[1][1] ? ranked[0][0] : null;
}

function numericSequence(values: string[]) {
  if (values.length < 2) return null;
  const parsed = values.map((value) => {
    const match = value.replaceAll(",", "").match(/[-+]?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : Number.NaN;
  });
  if (parsed.some((value) => !Number.isFinite(value))) return null;
  return parsed;
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const working = products.map((product) => {
    const options = [...product.options].sort((a, b) => a.position - b.position);
    const normalizedSequence = options.map((option) =>
      canonicalOptionName(option.name),
    );
    return {
      ...product,
      options,
      normalizedSequence,
      displaySequence: options.length
        ? options.map((option) => option.name).join(" → ")
        : "No options",
      issueKeys: [] as IssueKey[],
      findings: [] as string[],
    };
  });

  const comparableGroups = new Map<string, typeof working>();
  for (const product of working) {
    const groupKey = [...product.normalizedSequence].sort().join("|");
    if (
      !groupKey ||
      unique(product.normalizedSequence).length !==
        product.normalizedSequence.length
    ) {
      continue;
    }
    const current = comparableGroups.get(groupKey) ?? [];
    current.push(product);
    comparableGroups.set(groupKey, current);
  }

  for (const group of comparableGroups.values()) {
    if (group.length < 2) continue;
    const sequences = group.map((product) =>
      product.normalizedSequence.join(" → "),
    );
    const uniqueSequences = unique(sequences);
    if (uniqueSequences.length < 2) continue;
    const baseline = strictMode(sequences);
    for (const product of group) {
      const sequence = product.normalizedSequence.join(" → ");
      if (!baseline || sequence !== baseline) {
        product.issueKeys.push("sequence_mismatch");
        product.findings.push(
          baseline
            ? `Option order is ${sequence}; the common sequence in comparable products is ${baseline}.`
            : `Comparable products use multiple option sequences: ${uniqueSequences.join(" / ")}.`,
        );
      }
    }
  }

  const familyUsages = new Map<
    string,
    Array<{ product: (typeof working)[number]; raw: string; display: string }>
  >();

  for (const product of working) {
    for (const option of product.options) {
      const family = canonicalOptionName(option.name);
      if (!family) continue;
      const current = familyUsages.get(family) ?? [];
      current.push({
        product,
        raw: rawKey(option.name),
        display: option.name.trim(),
      });
      familyUsages.set(family, current);
    }
  }

  for (const [family, usages] of familyUsages) {
    const rawForms = unique(usages.map((usage) => usage.raw));
    if (rawForms.length < 2) continue;
    const baseline = strictMode(usages.map((usage) => usage.raw));
    const displayForms = unique(usages.map((usage) => usage.display)).join(", ");
    for (const usage of usages) {
      if (!baseline || usage.raw !== baseline) {
        usage.product.issueKeys.push("name_drift");
        usage.product.findings.push(
          `Option family "${family}" uses multiple labels in the catalog: ${displayForms}.`,
        );
      }
    }
  }

  for (const product of working) {
    const seen = new Set<string>();
    const duplicates = new Set<string>();
    for (const family of product.normalizedSequence) {
      if (seen.has(family)) duplicates.add(family);
      seen.add(family);
    }
    if (duplicates.size) {
      product.issueKeys.push("duplicate_option_family");
      product.findings.push(
        `Duplicate option families detected: ${[...duplicates].join(", ")}.`,
      );
    }

    for (const option of product.options) {
      const parsed = numericSequence(option.values);
      if (!parsed) continue;
      const sorted = [...parsed].sort((a, b) => a - b);
      if (parsed.some((value, index) => value !== sorted[index])) {
        product.issueKeys.push("numeric_value_order");
        product.findings.push(
          `${option.name} values appear as ${option.values.join(" → ")}; review the intended numeric order.`,
        );
      }
    }
  }

  const auditedProducts: ProductAudit[] = working.map((product) => ({
    ...product,
    issueKeys: unique(product.issueKeys),
    findings: unique(product.findings),
    status: product.issueKeys.length ? "Review structure" : "Consistent",
  }));

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => ({
      ...ISSUE_DEFINITIONS[key],
      affectedProducts: auditedProducts.filter((product) =>
        product.issueKeys.includes(key),
      ).length,
    }))
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
        b.issueKeys.length - a.issueKeys.length ||
        a.title.localeCompare(b.title),
    ),
    rankedIssues,
    summary: {
      productsScanned: auditedProducts.length,
      optionsScanned: auditedProducts.reduce(
        (total, product) => total + product.options.length,
        0,
      ),
      productsWithIssues: auditedProducts.filter(
        (product) => product.issueKeys.length,
      ).length,
      consistentProducts: auditedProducts.filter(
        (product) => !product.issueKeys.length,
      ).length,
      sequenceIssues: auditedProducts.filter((product) =>
        product.issueKeys.includes("sequence_mismatch"),
      ).length,
      namingDriftIssues: auditedProducts.filter((product) =>
        product.issueKeys.includes("name_drift"),
      ).length,
      numericOrderReviews: auditedProducts.filter((product) =>
        product.issueKeys.includes("numeric_value_order"),
      ).length,
    },
  };
}

function protectCsvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildRemediationCsv(audit: AuditResult) {
  const rows: Array<Array<string | number>> = [
    [
      "Priority",
      "Issue",
      "Product",
      "Product admin link",
      "Current option order",
      "Finding",
      "Recommended next step",
    ],
  ];

  for (const product of audit.products) {
    for (const key of product.issueKeys) {
      const issue = ISSUE_DEFINITIONS[key];
      const relatedFindings = product.findings.filter((finding) => {
        if (key === "sequence_mismatch")
          return (
            finding.startsWith("Option order") ||
            finding.startsWith("Comparable")
          );
        if (key === "name_drift") return finding.startsWith("Option family");
        if (key === "duplicate_option_family")
          return finding.startsWith("Duplicate");
        return finding.includes("values appear as");
      });
      rows.push([
        issue.priority,
        issue.label,
        product.title,
        `shopify://admin/products/${product.legacyResourceId}`,
        product.displaySequence,
        relatedFindings.join(" "),
        issue.recommendation,
      ]);
    }
  }

  return `\uFEFF${rows
    .map((row) => row.map(protectCsvCell).join(","))
    .join("\r\n")}\r\n`;
}
