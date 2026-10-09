export const appMeta={
  shortName:"Zero Price Variant Guard",exportSlug:"zero-price-variant",readonlyLabel:"Read-only · Catalog QA",
  eyebrow:"CATALOG QA / REVIEW",headline:"Zero Price Variant Guard",lead:"Identify zero-priced product variants for merchant review.",
  sidebarHelp:"Review flagged products and choose whether to update them.",
  readOnlyNote:"This app does not alter products or prices.",
  panelTitle:"Catalog findings",emptyCopy:"No matching issues were found in this product batch."
} as const;
export type Finding={productId:string;productTitle:string;rule:"issue";evidence:string;detail:string};
export const rules={issue:{label:"Zero-priced variant",priority:"Review",advice:"Review whether each zero-priced variant is intentional."}} as const;
export function auditCatalog(rows:any[]){
  const findings:Finding[]=[];
  for(const p of rows){const variants=Array.isArray(p.variants?.nodes)?p.variants.nodes:[];
const zero=variants.filter((v:any)=>typeof v.price==="string"&&v.price.trim()!==""&&Number(v.price)===0).length;
if(zero>0)findings.push({productId:p.id,productTitle:p.title,rule:"issue",evidence:zero+" zero-priced variant(s)",detail:"Review "+zero+" variant(s) listed with a price of zero."});}
  findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));
  return {products:rows.length,findings,skipped:[] as string[]};
}
export function buildCsv(findings:Finding[]){
  const cell=(s:string)=>'"'+(/^[\s]*[=+@\-\t\r\n]/.test(s)?"'"+s:s).replace(/"/g,'""')+'"';
  return "\ufeff"+[["Priority","Product","Product ID","Finding","Evidence","Recommendation"],...findings.map(f=>["Review",f.productTitle,f.productId,rules.issue.label,f.evidence,rules.issue.advice])].map(r=>r.map(v=>cell(String(v))).join(",")).join("\r\n");
}
