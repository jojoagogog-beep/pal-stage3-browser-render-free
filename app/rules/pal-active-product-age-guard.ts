export const appMeta = {
 shortName:"Active Product Age Guard",
 exportSlug:"active-product-age",
 readonlyLabel:"Read-only · Product freshness QA",
 eyebrow:"CATALOG QA / REVIEW",
 headline:"Active Product Age Guard",
 lead:"Find active products that have not been updated for more than 365 days.",
 sidebarHelp:"Review any stale active product and decide whether an update is needed.",
 readOnlyNote:"This app never modifies merchant data.",
 panelTitle:"Stale active products",
 emptyCopy:"No stale active products found in this catalog batch.",
 entityKind:"product"
} as const;
export type Finding={productId:string;productTitle:string;rule:string;evidence:string;detail:string};
export const rules={issue:{label:"Active product last updated over 365 days ago",priority:"Review",advice:"Review the active listing for accuracy and refresh it where appropriate."}};
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];const skipped:string[]=[];
 for(const p of rows){
   if(p.status!=="ACTIVE")continue;
   const timestamp=Date.parse(String(p.updatedAt||""));
   if(!Number.isFinite(timestamp)){skipped.push(String(p.id||""));continue;}
   const days=Math.floor((Date.now()-timestamp)/86400000);
   if(days>365)findings.push({productId:p.id,productTitle:p.title,rule:"issue",evidence:days+" days since last update",detail:"This active product has not been updated for "+days+" days."});
 }
 findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));
 return {products:rows.length,findings,skipped};
}
export function buildCsv(findings:Finding[]){
 const cell=(v:string)=>'"'+(/^[\s]*[=+@\-\t\r\n]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';
 return "\uFEFF"+[["Priority","Product","Admin ID","Finding","Evidence","Recommended action"],...findings.map(f=>["Review",f.productTitle,f.productId,rules.issue.label,f.evidence,rules.issue.advice])].map(row=>row.map(v=>cell(String(v))).join(",")).join("\r\n");
}
