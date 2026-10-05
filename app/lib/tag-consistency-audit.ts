export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  tags: string[];
};

export type TagEvidence = {
  productId: string;
  productLegacyId: string;
  productTitle: string;
  originalTag: string;
  normalizedTag: string;
};

export type Finding = {
  normalizedTag: string;
  observedTags: string[];
  affectedProducts: number;
  examples: TagEvidence[];
  reason: string;
  priority: "High" | "Review";
};

export type AuditResult = {
  findings: Finding[];
  summary: {
    productsScanned: number;
    tagValuesScanned: number;
    inconsistentGroups: number;
    affectedProducts: number;
  };
};

export function normalizeTag(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-./,&'’]+/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

function reasonFor(values: string[]) {
  const trimmed = values.map((v) => v.trim());
  const lower = new Set(trimmed.map((v) => v.toLowerCase()));
  const compact = new Set(trimmed.map((v) =>
    v.toLowerCase().replace(/[\s_\-./,&'’]+/g, "")));
  if (lower.size === 1) return "Tags differ only by capitalization.";
  if (compact.size === 1) return "Tags differ only by spacing or punctuation.";
  return "Tags collapse to the same normalized form.";
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const groups = new Map<string, TagEvidence[]>();
  let tagValuesScanned = 0;

  for (const product of products) {
    for (const raw of product.tags || []) {
      const tag = raw.trim();
      if (!tag) continue;
      tagValuesScanned++;
      const normalizedTag = normalizeTag(tag);
      if (!normalizedTag) continue;
      const evidence: TagEvidence = {
        productId: product.id,
        productLegacyId: product.legacyResourceId,
        productTitle: product.title,
        originalTag: tag,
        normalizedTag,
      };
      const arr = groups.get(normalizedTag) || [];
      arr.push(evidence);
      groups.set(normalizedTag, arr);
    }
  }

  const findings: Finding[] = [];
  for (const [normalizedTag, evidence] of groups) {
    const observedTags = [...new Set(evidence.map((e) => e.originalTag))]
      .sort((a, b) => a.localeCompare(b));
    if (observedTags.length < 2) continue;
    findings.push({
      normalizedTag,
      observedTags,
      affectedProducts: new Set(evidence.map((e) => e.productId)).size,
      examples: evidence.slice(0, 16),
      reason: reasonFor(observedTags),
      priority: evidence.length >= 5 ? "High" : "Review",
    });
  }

  findings.sort((a, b) =>
    (b.priority === "High" ? 1 : 0) - (a.priority === "High" ? 1 : 0) ||
    b.affectedProducts - a.affectedProducts ||
    a.normalizedTag.localeCompare(b.normalizedTag));

  const affectedProducts = new Set(
    findings.flatMap((f) => f.examples.map((e) => e.productId))
  ).size;

  return {
    findings,
    summary: {
      productsScanned: products.length,
      tagValuesScanned,
      inconsistentGroups: findings.length,
      affectedProducts,
    },
  };
}

function csvCell(v: unknown) {
  let s = v == null ? "" : String(v).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}

export function buildRemediationCsv(audit: AuditResult) {
  const rows: unknown[][] = [[
    "Priority", "Observed tags", "Reason", "Product",
    "Product admin link", "Observed tag", "Normalized form"
  ]];
  for (const finding of audit.findings) {
    for (const evidence of finding.examples) {
      rows.push([
        finding.priority,
        finding.observedTags.join(" | "),
        finding.reason,
        evidence.productTitle,
        "shopify://admin/products/" + evidence.productLegacyId,
        evidence.originalTag,
        evidence.normalizedTag,
      ]);
    }
  }
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
