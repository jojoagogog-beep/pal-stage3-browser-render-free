export type SelectedOption = { name: string; value: string };
export type VariantInput = { id: string; legacyResourceId: string; title: string; sku?: string | null; selectedOptions: SelectedOption[] };
export type ProductInput = { id: string; legacyResourceId: string; title: string; variants: VariantInput[] };

export type VariantEvidence = {
  productId: string; productLegacyId: string; productTitle: string;
  variantId: string; variantLegacyId: string; variantTitle: string;
  optionName: string; originalValue: string; normalizedValue: string;
};

export type Finding = {
  optionName: string;
  normalizedValue: string;
  observedValues: string[];
  affectedProducts: number;
  affectedVariants: number;
  examples: VariantEvidence[];
  reason: string;
  priority: "High" | "Review";
};

export type AuditResult = {
  findings: Finding[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    optionValuesScanned: number;
    inconsistentGroups: number;
    affectedProducts: number;
    affectedVariants: number;
  };
};

const alias: Record<string,string> = {
  gray:"grey", charcoalgray:"charcoalgrey",
  xlarge:"xl", extralarge:"xl", xlarg:"xl",
  xsmall:"xs", extrasmall:"xs",
  xxlarge:"xxl", extraextralarge:"xxl",
  xxsmall:"xxs", extraextrasmall:"xxs",
};

export function normalizeOptionValue(value: string): string {
  const compact = value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-./]+/g, "")
    .replace(/[^a-z0-9]+/g, "");
  return alias[compact] || compact;
}

function reasonFor(values: string[]) {
  const lower = new Set(values.map(v => v.toLowerCase()));
  const compact = new Set(values.map(v => v.toLowerCase().replace(/[\s_\-./]+/g, "")));
  if (lower.size === 1) return "Values differ only by case.";
  if (compact.size === 1) return "Values differ only by spacing or punctuation.";
  return "Values map to the same common normalized form.";
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const groups = new Map<string, VariantEvidence[]>();
  let variantsScanned = 0, optionValuesScanned = 0;
  for (const p of products) {
    for (const v of p.variants) {
      variantsScanned++;
      for (const o of v.selectedOptions || []) {
        optionValuesScanned++;
        const normalized = normalizeOptionValue(o.value);
        if (!normalized) continue;
        const key = `${o.name.trim().toLowerCase()}::${normalized}`;
        const ev: VariantEvidence = {
          productId:p.id, productLegacyId:p.legacyResourceId, productTitle:p.title,
          variantId:v.id, variantLegacyId:v.legacyResourceId, variantTitle:v.title,
          optionName:o.name.trim(), originalValue:o.value, normalizedValue:normalized,
        };
        const arr = groups.get(key) || []; arr.push(ev); groups.set(key, arr);
      }
    }
  }

  const findings: Finding[] = [];
  for (const [, evs] of groups) {
    const values = [...new Set(evs.map(e => e.originalValue))];
    if (values.length < 2) continue;
    const productIds = new Set(evs.map(e => e.productId));
    const variantIds = new Set(evs.map(e => e.variantId));
    findings.push({
      optionName: evs[0].optionName,
      normalizedValue: evs[0].normalizedValue,
      observedValues: values.sort((a,b)=>a.localeCompare(b)),
      affectedProducts: productIds.size,
      affectedVariants: variantIds.size,
      examples: evs.slice(0,8),
      reason: reasonFor(values),
      priority: variantIds.size >= 4 || productIds.size >= 3 ? "High" : "Review",
    });
  }
  findings.sort((a,b) => (b.priority==="High"?1:0)-(a.priority==="High"?1:0) || b.affectedVariants-a.affectedVariants || a.optionName.localeCompare(b.optionName));
  const affectedProducts = new Set(findings.flatMap(f => f.examples.map(e => e.productId))).size;
  const affectedVariants = new Set(findings.flatMap(f => f.examples.map(e => e.variantId))).size;
  return {findings, summary:{productsScanned:products.length, variantsScanned, optionValuesScanned, inconsistentGroups:findings.length, affectedProducts, affectedVariants}};
}

function csvCell(v: unknown) {
  let s = v == null ? "" : String(v).replaceAll("\r"," ").replaceAll("\n"," ");
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return `"${s.replaceAll('"','""')}"`;
}
export function buildRemediationCsv(audit: AuditResult) {
  const rows: unknown[][] = [["Priority","Option","Observed values","Reason","Product","Product admin link","Variant","Observed option value","Normalized form"]];
  for (const f of audit.findings) for (const e of f.examples) rows.push([
    f.priority,f.optionName,f.observedValues.join(" | "),f.reason,e.productTitle,
    `shopify://admin/products/${e.productLegacyId}`,e.variantTitle,e.originalValue,e.normalizedValue
  ]);
  return rows.map(r=>r.map(csvCell).join(",")).join("\n");
}
