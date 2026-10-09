import {Form} from "react-router";
import type {AuditResult} from "../lib/product-audit";
import {productAdminUrl} from "../lib/product-audit";
import styles from "./product-audit-dashboard.module.css";
type Props={appName:string;mode:string;audit:AuditResult;shopDomain:string;shopName:string;scannedAt:string;coverageLimited?:boolean;showExport?:boolean;demo?:boolean};
export function ProductAuditDashboard({appName,audit,shopDomain,shopName,scannedAt,coverageLimited=false,showExport=true,demo=false}:Props){
 return <s-page heading={appName} inlineSize="large">
  <s-button slot="primary-action" variant="primary" onClick={()=>window.location.reload()}>Run audit again</s-button>
  {showExport?<Form method="post" reloadDocument slot="secondary-actions"><input type="hidden" name="intent" value="exportCsv"/><s-button type="submit" variant="secondary">Export diagnostic CSV</s-button></Form>:null}
  {demo?<s-banner heading="Sample catalog audit" tone="info">This public preview uses fictional product records and the same read-only audit logic as the installed app.</s-banner>:null}
  <s-banner heading="Read-only product audit" tone="info">The app reads product data for diagnostics and never edits products.</s-banner>
  {coverageLimited?<s-banner heading="Safety limit reached" tone="warning">This run reached the synchronous product scan limit.</s-banner>:null}
  <s-section heading="Audit summary"><s-stack direction="block" gap="base"><s-paragraph>{shopName} · Scanned {audit.products.length} products at {scannedAt}.</s-paragraph><div className={styles.metrics}><div className={styles.metric}><span>Products scanned</span><strong>{audit.products.length}</strong></div><div className={styles.metricWarning}><span>Products to review</span><strong>{new Set(audit.findings.map(f=>f.product.id)).size}</strong></div><div className={styles.metric}><span>Clean products</span><strong>{audit.cleanCount}</strong></div><div className={styles.metric}><span>Findings</span><strong>{audit.findings.length}</strong></div></div></s-stack></s-section>
  <s-section heading="Products to review">{audit.findings.length===0?<s-banner heading="No findings" tone="success">No matching review conditions were found in this scan.</s-banner>:<s-table variant="auto"><s-table-header-row><s-table-header listSlot="primary">Product</s-table-header><s-table-header>Issue</s-table-header><s-table-header>Detail</s-table-header></s-table-header-row><s-table-body>{audit.findings.slice(0,100).map((f,i)=><s-table-row key={f.product.id+"-"+i}><s-table-cell><a className={styles.productLink} href={demo?"#product-"+f.product.legacyResourceId:productAdminUrl(shopDomain,f.product.legacyResourceId)} target={demo?undefined:"_blank"} rel={demo?undefined:"noreferrer"}>{f.product.title}</a></s-table-cell><s-table-cell>{f.reason}</s-table-cell><s-table-cell>{f.detail}</s-table-cell></s-table-row>)}</s-table-body></s-table>}</s-section>
 </s-page>;
}
