export const appMeta={
  shortName:"Variant Price Range Guard",exportSlug:"variant-price-range",readonlyLabel:"Read-only · Catalog QA",
  eyebrow:"CATALOG QA / REVIEW",headline:"Variant Price Range Guard",lead:"Find products with unusually wide price spreads across variants.",
  sidebarHelp:"Review flagged products and choose whether to update them.",
  readOnlyNote:"This app does not alter products or prices.",
  panelTitle:"Catalog findings",emptyCopy:"No matching issues were found in this product batch."
} as const;
export type Finding={productId:string;productTitle:string;rule:"issue";evidence:string;detail:string};
export const rules={issue:{label:"Wide variant price range",priority:"Review",advice:"Review the variant prices for pricing accuracy."}} as const;
export function auditCatalog(rows:any[]){
  const findings:Finding[]=[];
  for(const p of rows){const variants=Array.isArray(p.variants?.nodes)?p.variants.nodes:[];
const amounts=variants.map((v:any)=>Number(v.price)).filter((v:number)=>Number.isFinite(v)&&v>=0);
if(amounts.length<2)continue;
const low=Math.min(...amounts),high=Math.max(...amounts);
if((low===0&&high>0)||(low>0&&high/low>=3)) {
  findings.push({productId:p.id,productTitle:p.title,rule:"issue",evidence:low.toFixed(2)+" to "+high.toFixed(2),detail:"Variant price range needs review: "+low.toFixed(2)+" to "+high.toFixed(2)});
}}
  findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));
  return {products:rows.length,findings,skipped:[] as string[]};
}
export function buildCsv(findings:Finding[]){
  const cell=(s:string)=>'"'+(/^[\s]*[=+@\-\t\r\n]/.test(s)?"'"+s:s).replace(/"/g,'""')+'"';
  return "\ufeff"+[["Priority","Product","Product ID","Finding","Evidence","Recommendation"],...findings.map(f=>["Review",f.productTitle,f.productId,rules.issue.label,f.evidence,rules.issue.advice])].map(r=>r.map(v=>cell(String(v))).join(",")).join("\r\n");
}
