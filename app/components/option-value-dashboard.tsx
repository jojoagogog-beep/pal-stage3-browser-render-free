import { Form } from "react-router";
import type { AuditResult } from "../lib/option-value-audit";
import styles from "./variant-dashboard.module.css";

type Props={audit:AuditResult;shopName:string;scannedAt:string;coverageLimited?:boolean;showExport?:boolean;demo?:boolean};
export function OptionValueDashboard({audit,shopName,scannedAt,coverageLimited=false,showExport=true,demo=false}:Props){
 return <s-page heading="Option Value Guard" inlineSize="large">
  <s-button slot="primary-action" variant="primary" onClick={()=>window.location.reload()}>Run audit again</s-button>
  {showExport?<Form method="post" reloadDocument slot="secondary-actions"><input type="hidden" name="intent" value="exportCsv"/><s-button type="submit" variant="secondary">Export diagnostic CSV</s-button></Form>:null}
  {demo?<s-banner heading="Reviewer demo" tone="info">This public demo uses fictional option values with the same local normalization rules as the installed app.</s-banner>:null}
  {coverageLimited?<s-banner heading="Large catalog safety limit reached" tone="warning">This run stopped at its safety limit. Results and CSV cover only the products scanned.</s-banner>:null}
  <s-section heading="Catalog option-value consistency audit"><s-stack direction="block" gap="base">
   <s-paragraph>{shopName} · Scanned {audit.summary.productsScanned} products, {audit.summary.variantsScanned} variants, and {audit.summary.optionValuesScanned} option values at {scannedAt}.</s-paragraph>
   <s-paragraph>Read-only audit. Option Value Guard highlights likely naming drift and never edits products, variants, option values, inventory, themes, or customer data.</s-paragraph>
   <div className={styles.metrics}>
    <div className={styles.metric}><span>Inconsistent groups</span><strong>{audit.summary.inconsistentGroups}</strong></div>
    <div className={styles.metric}><span>Affected products</span><strong>{audit.summary.affectedProducts}</strong></div>
    <div className={styles.metric}><span>Affected variants</span><strong>{audit.summary.affectedVariants}</strong></div>
   </div>
  </s-stack></s-section>
  <s-section heading="Groups to review">
   {audit.findings.length===0?<s-banner heading="No checked naming inconsistencies found" tone="success">This run found no option values that collapse to the same checked normalized form.</s-banner>:
   <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Option / observed values</s-table-header><s-table-header listSlot="labeled">Priority</s-table-header><s-table-header format="numeric">Products</s-table-header><s-table-header format="numeric">Variants</s-table-header><s-table-header>Why flagged</s-table-header></s-table-header-row><s-table-body>
    {audit.findings.map((f,i)=><s-table-row key={f.optionName+"-"+f.normalizedValue+"-"+i}><s-table-cell><s-text type="strong">{f.optionName}</s-text><br/>{f.observedValues.join(" · ")}</s-table-cell><s-table-cell><s-badge tone={f.priority==="High"?"warning":"info"}>{f.priority}</s-badge></s-table-cell><s-table-cell>{f.affectedProducts}</s-table-cell><s-table-cell>{f.affectedVariants}</s-table-cell><s-table-cell>{f.reason}</s-table-cell></s-table-row>)}
   </s-table-body></s-table>}
  </s-section>
  <s-section heading="Evidence">
   <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Product / variant</s-table-header><s-table-header>Option</s-table-header><s-table-header>Observed value</s-table-header><s-table-header>Normalized form</s-table-header></s-table-header-row><s-table-body>
    {audit.findings.flatMap((f,fi)=>f.examples.map((e,ei)=><s-table-row key={fi+"-"+ei}><s-table-cell>{demo?<span>{e.productTitle} · {e.variantTitle}</span>:<a className={styles.productLink} href={`shopify://admin/products/${e.productLegacyId}`} target="_top">{e.productTitle} · {e.variantTitle}</a>}</s-table-cell><s-table-cell>{e.optionName}</s-table-cell><s-table-cell>{e.originalValue}</s-table-cell><s-table-cell>{e.normalizedValue}</s-table-cell></s-table-row>))}
   </s-table-body></s-table>
  </s-section>
  <s-section heading="What this audit checks"><s-unordered-list>
   <s-list-item>Case-only differences such as Blue vs blue.</s-list-item>
   <s-list-item>Spacing or punctuation differences such as X-Large vs X Large.</s-list-item>
   <s-list-item>A small set of common equivalents such as Gray/Grey and Extra Large/XL.</s-list-item>
   <s-list-item>Findings are heuristic and may be intentional; merchants decide whether to edit catalog values.</s-list-item>
  </s-unordered-list></s-section>
  <div className={styles.footerLinks}><a href="/privacy" target="_blank" rel="noreferrer">Privacy</a><a href="/terms" target="_blank" rel="noreferrer">Terms</a><a href="/support" target="_blank" rel="noreferrer">Support</a></div>
 </s-page>
}
