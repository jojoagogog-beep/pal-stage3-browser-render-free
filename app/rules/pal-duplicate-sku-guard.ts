import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Duplicate SKU Guard","duplicate-sku",
  "Find exact duplicates and case/spacing collisions across up to 1,000 store variants; review product variants without modifying them.");
export const rules={
  exact_duplicate:{label:"Exact duplicate SKU",priority:"Review",advice:"Confirm whether these variants should share this SKU before updating any catalog record."},
  normalized_collision:{label:"Case or spacing SKU collision",priority:"Review",advice:"Confirm the intended SKU naming before standardizing capitalization or spacing."}
} as const;
type Variant={id:string;title:string;sku:string|null};
type Product={id:string;title:string;variants?:{pageInfo?:{hasNextPage?:boolean};nodes?:Variant[]}};
const canonical=(v:string)=>v.trim().replace(/\s+/g," ").toLocaleUpperCase("en-US");
export function auditCatalog(rows:Product[]){
 const findings:Finding[]=[],skipped:string[]=[];
 const buckets=new Map<string,Array<{productId:string;productTitle:string;variantTitle:string;sku:string}>>();
 for(const p of rows){
  if(p.variants?.pageInfo?.hasNextPage){
   skipped.push(String(p.title||p.id)+": more than 40 variants; product omitted to prevent incomplete results");continue;
  }
  for(const v of p.variants?.nodes||[]){
   const sku=String(v.sku||"").trim();if(!sku)continue;
   const key=canonical(sku),a=buckets.get(key)||[];
   a.push({productId:p.id,productTitle:p.title,variantTitle:v.title,sku});buckets.set(key,a);
  }
 }
 for(const values of buckets.values()){
  if(values.length<2)continue;
  const kind=new Set(values.map(v=>v.sku)).size===1?"exact_duplicate":"normalized_collision";
  const names=[...new Set(values.map(v=>v.sku))].sort().join(" / ");
  for(const v of values)findings.push({
   productId:v.productId,productTitle:v.productTitle,rule:kind,
   evidence:"Variant "+v.variantTitle+" — "+v.sku,
   detail:values.length+" variants share normalized SKU "+names+" within this catalog batch."
  });
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
