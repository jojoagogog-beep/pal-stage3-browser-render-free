import { Form } from "react-router";
import type { AuditResult } from "../lib/vendor-name-audit";
import styles from "./variant-dashboard.module.css";

type Props={audit:AuditResult;shopName:string;scannedAt:string;coverageLimited?:boolean;showExport?:boolean;demo?:boolean};

export function VendorNameDashboard({audit,shopName,scannedAt,coverageLimited=false,showExport=true,demo=false}:Props){
 return <s-page heading="Vendor Name Guard" inlineSize="large">
  <s-button slot="primary-action" variant="primary" onClick={()=>window.location.reload()}>Run audit again</s-button>
  {showExport?<Form method="post" reloadDocument slot="secondary-actions"><input type="hidden" name="intent" value="exportCsv"/><s-button type="submit" variant="secondary">Export diagnostic CSV</s-button></Form>:null}
  {demo?<s-banner heading="Reviewer demo" tone="info">This public demo uses fictional vendor names with the same local normalization rules as the installed app.</s-banner>:null}
  {coverageLimited?<s-banner heading="Large catalog safety limit reached" tone="warning">This run stopped at its safety limit. Results and CSV cover only the products scanned.</s-banner>:null}

  <s-section heading="Vendor naming consistency audit"><s-stack direction="block" gap="base">
   <s-paragraph>{shopName} · Scanned {audit.summary.productsScanned} products and {audit.summary.vendorValuesScanned} populated vendor values at {scannedAt}.</s-paragraph>
   <s-paragraph>Read-only audit. Vendor Name Guard highlights likely naming drift and never edits products, vendor fields, themes, orders, or customer data.</s-paragraph>
   <div className={styles.metrics}>
    <div className={styles.metric}><span>Inconsistent groups</span><strong>{audit.summary.inconsistentGroups}</strong></div>
    <div className={styles.metric}><span>Affected products</span><strong>{audit.summary.affectedProducts}</strong></div>
    <div className={styles.metric}><span>Vendor values checked</span><strong>{audit.summary.vendorValuesScanned}</strong></div>
   </div>
  </s-stack></s-section>

  <s-section heading="Vendor groups to review">
   {audit.findings.length===0?<s-banner heading="No checked naming inconsistencies found" tone="success">This run found no vendor names that collapse to the same checked normalized form.</s-banner>:
   <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Observed vendor names</s-table-header><s-table-header listSlot="labeled">Priority</s-table-header><s-table-header format="numeric">Products</s-table-header><s-table-header>Why flagged</s-table-header></s-table-header-row><s-table-body>
    {audit.findings.map((f,i)=><s-table-row key={f.normalizedVendor+"-"+i}><s-table-cell><s-text type="strong">{f.observedVendors.join(" · ")}</s-text></s-table-cell><s-table-cell><s-badge tone={f.priority==="High"?"warning":"info"}>{f.priority}</s-badge></s-table-cell><s-table-cell>{f.affectedProducts}</s-table-cell><s-table-cell>{f.reason}</s-table-cell></s-table-row>)}
   </s-table-body></s-table>}
  </s-section>

  <s-section heading="Evidence">
   <s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Product</s-table-header><s-table-header>Observed vendor</s-table-header><s-table-header>Normalized form</s-table-header></s-table-header-row><s-table-body>
    {audit.findings.flatMap((f,fi)=>f.examples.map((e,ei)=><s-table-row key={fi+"-"+ei}><s-table-cell>{demo?<span>{e.productTitle}</span>:<a className={styles.productLink} href={`shopify://admin/products/${e.productLegacyId}`} target="_top">{e.productTitle}</a>}</s-table-cell><s-table-cell>{e.originalVendor}</s-table-cell><s-table-cell>{e.normalizedVendor}</s-table-cell></s-table-row>))}
   </s-table-body></s-table>
  </s-section>

  <s-section heading="What this audit checks"><s-unordered-list>
   <s-list-item>Capitalization-only differences such as ACME vs Acme.</s-list-item>
   <s-list-item>Spacing or punctuation differences such as North-Star vs North Star.</s-list-item>
   <s-list-item>Findings are heuristic. Similar-looking names may intentionally refer to different vendors.</s-list-item>
   <s-list-item>Merchants decide whether any vendor field should be changed.</s-list-item>
  </s-unordered-list></s-section>

  <div className={styles.footerLinks}><a href="/privacy" target="_blank" rel="noreferrer">Privacy</a><a href="/terms" target="_blank" rel="noreferrer">Terms</a><a href="/support" target="_blank" rel="noreferrer">Support</a></div>
 </s-page>
}
