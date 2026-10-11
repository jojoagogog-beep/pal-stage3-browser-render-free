import {auditCatalog as auditSeo,ISSUE_DEFINITIONS,type ProductInput,type IssueKey} from "./seo-fallback-audit";
export const appMeta={
  shortName:"SEO Fallback Guard",exportSlug:"seo-fallback",readonlyLabel:"Read-only · SEO fallback audit",
  eyebrow:"CATALOG SEO / REVIEW",headline:"SEO Fallback Readiness",
  lead:"Identify product SEO fields relying on fallbacks and review where source text may not be suitable.",
  sidebarHelp:"Inspect fallback descriptions, titles, and partially customized metadata.",
  readOnlyNote:"This tool only reads product fields. It never modifies merchant data.",
  panelTitle:"SEO fallback findings",
  emptyCopy:"No SEO fallback concerns detected for the current product batch.",
  entityKind:"product"
} as const;
export const rules=Object.fromEntries(Object.entries(ISSUE_DEFINITIONS).map(([k,v])=>[k,{label:v.label,priority:v.priority,advice:v.recommendation}])) as Record<IssueKey,{label:string;priority:string;advice:string}>;
type Finding={productId:string;productTitle:string;rule:IssueKey;evidence:string;detail:string};
export function auditCatalog(rows:any[]){
 const inputs:ProductInput[]=rows.map((p:any)=>({id:String(p.id),legacyResourceId:String(p.legacyResourceId||p.id).split("/").pop()||"",
 title:String(p.title||""),description:String(p.description||""),
 seoTitle:p.seo?.title??null,seoDescription:p.seo?.description??null}));
 const out=auditSeo(inputs);const findings:Finding[]=[];
 for(const p of out.products)for(const key of p.issueKeys) {
  findings.push({productId:p.id,productTitle:p.title,rule:key,
   evidence:[p.seoTitle||"(fallback title)",p.seoDescription||"(fallback description)"].join(" / ").slice(0,350),
   detail:p.findings.join("; ").slice(0,900)||rules[key].label});
 }
 return {products:rows.length,findings,skipped:[]};
}
export function buildCsv(findings:Finding[]){
 const safe=(v:string)=>'"'+(/^[\s=+@-]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';
 const lines=[["Product","Product ID","SEO issue","Evidence","Recommended action"],
  ...findings.map(f=>[f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])];
 return "\uFEFF"+lines.map(row=>row.map(v=>safe(String(v))).join(",")).join("\r\n");
}
