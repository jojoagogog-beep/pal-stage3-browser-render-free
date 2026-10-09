import { Form } from "react-router";
import type { AuditResult, ProductAudit, WeightValue } from "../lib/variant-shipping-policy-audit";
import styles from "./variant-dashboard.module.css";

type Props = { audit: AuditResult; shopName: string; scannedAt: string; coverageLimited?: boolean; showExport?: boolean; demo?: boolean };
function productHref(product: ProductAudit, demo: boolean) { return demo ? `/review-demo#${product.legacyResourceId}` : `shopify://admin/products/${product.legacyResourceId}`; }
function formatWeight(weight: WeightValue | null) {
  if (!weight) return "Not set";
  const labels: Record<string,string> = {GRAMS:"g",KILOGRAMS:"kg",OUNCES:"oz",POUNDS:"lb"};
  return `${Number(weight.value.toFixed(3))} ${labels[String(weight.unit).toUpperCase()] || weight.unit}`;
}
export function ShippingPolicyDashboard({ audit, shopName, scannedAt, coverageLimited=false, showExport=true, demo=false }: Props) {
  const visible = audit.products.slice(0,50);
  return <s-page heading="Variant Shipping Guard" inlineSize="large">
    <s-button slot="primary-action" variant="primary" onClick={() => window.location.reload()}>Run audit again</s-button>
    {showExport ? <Form method="post" reloadDocument slot="secondary-actions"><input type="hidden" name="intent" value="exportCsv"/><s-button type="submit" variant="secondary">Export diagnostic CSV</s-button></Form> : null}
    {demo ? <s-banner heading="Reviewer demo" tone="info">This public demo uses fictional variant shipping, weight, and inventory-tracking records with the same local audit rules as the installed app.</s-banner> : null}
    {coverageLimited ? <s-banner heading="Large catalog safety limit reached" tone="warning">This run stopped at its safety limit. Results and CSV cover only the products shown as scanned.</s-banner> : null}
    <s-section heading="Variant shipping-policy integrity audit"><s-stack direction="block" gap="base">
      <s-paragraph>{shopName} · Scanned {audit.summary.productsScanned} products and {audit.summary.variantsScanned} variants at {scannedAt}.</s-paragraph>
      <s-paragraph>Read-only audit. Variant Shipping Guard reports observed shipping, weight, and inventory-tracking signals and never changes products, inventory, fulfillment, shipping rates, or themes.</s-paragraph>
      <div className={styles.metrics}>
        <div className={styles.metric}><span>Products to review</span><strong>{audit.summary.productsWithIssues}</strong></div>
        <div className={styles.metric}><span>Mixed shipping state</span><strong>{audit.summary.mixedShippingProducts}</strong></div>
        <div className={styles.metric}><span>Missing/zero weight</span><strong>{audit.summary.missingWeightVariants}</strong></div>
      </div>
    </s-stack></s-section>
    <s-section heading="Prioritized findings">
      {audit.rankedIssues.length===0 ? <s-banner heading="No checked shipping-policy inconsistencies found" tone="success">This run found no mixed shipping-required state, missing/zero weight on physical variants, or mixed inventory-tracking state.</s-banner> :
      <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Finding</s-table-header><s-table-header listSlot="labeled">Priority</s-table-header><s-table-header format="numeric">Products</s-table-header><s-table-header>Recommended next step</s-table-header></s-table-header-row><s-table-body>
        {audit.rankedIssues.map(issue=><s-table-row key={issue.key}><s-table-cell><s-text type="strong">{issue.label}</s-text></s-table-cell><s-table-cell><s-badge tone={issue.priority==="High"?"critical":issue.priority==="Medium"?"warning":"info"}>{issue.priority}</s-badge></s-table-cell><s-table-cell>{issue.affectedProducts}</s-table-cell><s-table-cell>{issue.recommendation}</s-table-cell></s-table-row>)}
      </s-table-body></s-table>}
    </s-section>
    <s-section heading="Products to review">
      {visible.length===0 ? <s-paragraph>No products were returned for this store.</s-paragraph> : <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Product</s-table-header><s-table-header listSlot="labeled">Status</s-table-header><s-table-header>Physical variants</s-table-header><s-table-header>Tracked variants</s-table-header><s-table-header>Finding</s-table-header></s-table-header-row><s-table-body>
        {visible.map(p=><s-table-row key={p.id}><s-table-cell><a className={styles.productLink} href={productHref(p,demo)} target={demo?undefined:"_top"}>{p.title||"Untitled product"}</a></s-table-cell><s-table-cell><s-badge tone={p.status==="Consistent"?"success":"warning"}>{p.status}</s-badge></s-table-cell><s-table-cell>{p.variants.filter(v=>v.requiresShipping).length}/{p.variants.length}</s-table-cell><s-table-cell>{p.variants.filter(v=>v.tracked).length}/{p.variants.length}</s-table-cell><s-table-cell>{p.findings.length?p.findings.join(" · "):"None in checked policy signals"}</s-table-cell></s-table-row>)}
      </s-table-body></s-table>}
    </s-section>
    <s-section heading="Variant evidence"><s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Product / variant</s-table-header><s-table-header>Shipping</s-table-header><s-table-header>Weight</s-table-header><s-table-header>Inventory tracking</s-table-header></s-table-header-row><s-table-body>
      {visible.flatMap(p=>p.variants.map(v=><s-table-row key={`${p.id}-${v.id}`}><s-table-cell>{p.title} · {v.title}</s-table-cell><s-table-cell>{v.requiresShipping?"Physical shipping":"No physical shipping"}</s-table-cell><s-table-cell>{v.requiresShipping?formatWeight(v.weight):"Not required"}</s-table-cell><s-table-cell>{v.tracked?"Tracked":"Untracked"}</s-table-cell></s-table-row>))}
    </s-table-body></s-table></s-section>
    <s-section heading="What the audit checks"><s-unordered-list><s-list-item>Sibling variants that mix physical-shipping required and not-required states.</s-list-item><s-list-item>Physical-shipping variants with missing or zero weight.</s-list-item><s-list-item>Sibling variants that mix tracked and untracked inventory.</s-list-item><s-list-item>Findings are diagnostic only; merchants decide whether each difference is intentional.</s-list-item></s-unordered-list></s-section>
    <div className={styles.footerLinks}><a href="/privacy" target="_blank" rel="noreferrer">Privacy</a><a href="/terms" target="_blank" rel="noreferrer">Terms</a><a href="/support" target="_blank" rel="noreferrer">Support</a></div>
  </s-page>;
}
