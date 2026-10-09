export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  vendor: string;
};

export type ProductEvidence = {
  productId: string;
  productLegacyId: string;
  productTitle: string;
  originalVendor: string;
  normalizedVendor: string;
};

export type Finding = {
  normalizedVendor: string;
  observedVendors: string[];
  affectedProducts: number;
  examples: ProductEvidence[];
  reason: string;
  priority: "High" | "Review";
};

export type AuditResult = {
  findings: Finding[];
  summary: {
    productsScanned: number;
    vendorValuesScanned: number;
    inconsistentGroups: number;
    affectedProducts: number;
  };
};

export function normalizeVendor(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-./,&'’]+/g, "")
    .replace(/[^a-z0-9]+/g, "");
}

function reasonFor(values: string[]) {
  const trimmed = values.map(v => v.trim());
  const lower = new Set(trimmed.map(v => v.toLowerCase()));
  const compact = new Set(trimmed.map(v => v.toLowerCase().replace(/[\s_\-./,&'’]+/g, "")));
  if (lower.size === 1) return "Names differ only by capitalization.";
  if (compact.size === 1) return "Names differ only by spacing or punctuation.";
  return "Names collapse to the same normalized form.";
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const groups = new Map<string, ProductEvidence[]>();
  let vendorValuesScanned = 0;

  for (const product of products) {
    const vendor = (product.vendor || "").trim();
    if (!vendor) continue;
    vendorValuesScanned++;
    const normalizedVendor = normalizeVendor(vendor);
    if (!normalizedVendor) continue;
    const ev: ProductEvidence = {
      productId: product.id,
      productLegacyId: product.legacyResourceId,
      productTitle: product.title,
      originalVendor: vendor,
      normalizedVendor,
    };
    const arr = groups.get(normalizedVendor) || [];
    arr.push(ev);
    groups.set(normalizedVendor, arr);
  }

  const findings: Finding[] = [];
  for (const [normalizedVendor, evs] of groups) {
    const values = [...new Set(evs.map(e => e.originalVendor))].sort((a,b)=>a.localeCompare(b));
    if (values.length < 2) continue;
    findings.push({
      normalizedVendor,
      observedVendors: values,
      affectedProducts: evs.length,
      examples: evs.slice(0,12),
      reason: reasonFor(values),
      priority: evs.length >= 4 ? "High" : "Review",
    });
  }

  findings.sort((a,b) => (b.priority==="High"?1:0)-(a.priority==="High"?1:0) || b.affectedProducts-a.affectedProducts || a.normalizedVendor.localeCompare(b.normalizedVendor));
  const affectedProducts = new Set(findings.flatMap(f => f.examples.map(e => e.productId))).size;

  return {
    findings,
    summary: {
      productsScanned: products.length,
      vendorValuesScanned,
      inconsistentGroups: findings.length,
      affectedProducts,
    },
  };
}

function csvCell(v: unknown) {
  let s = v == null ? "" : String(v).replaceAll("\r"," ").replaceAll("\n"," ");
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return `"${s.replaceAll('"','""')}"`;
}

export function buildRemediationCsv(audit: AuditResult) {
  const rows: unknown[][] = [["Priority","Observed vendor names","Reason","Product","Product admin link","Observed vendor","Normalized form"]];
  for (const f of audit.findings) for (const e of f.examples) rows.push([
    f.priority,
    f.observedVendors.join(" | "),
    f.reason,
    e.productTitle,
    `shopify://admin/products/${e.productLegacyId}`,
    e.originalVendor,
    e.normalizedVendor,
  ]);
  return rows.map(r=>r.map(csvCell).join(",")).join("\n");
}
