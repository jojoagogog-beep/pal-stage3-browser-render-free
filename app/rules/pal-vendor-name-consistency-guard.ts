import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Vendor Name Guard","vendor-name","Review similar vendor names that differ only in capitalization, punctuation or spacing.");
export const rules={inconsistent:{label:"Inconsistent vendor spelling",priority:"Review",advice:"Choose one canonical vendor name and review the affected product records before editing."}} as const;
const normalize=(s:string)=>s.normalize("NFKC").trim().toLowerCase().replace(/[\s_\-./,&'’]+/g,"").replace(/[^a-z0-9]+/g,"");
export function auditCatalog(rows:any[]){
 const groups=new Map<string,Array<{id:string;title:string;vendor:string}>>();
 for(const p of rows){
  const vendor=String(p.vendor||"").trim();if(!vendor)continue;
  const normalized=normalize(vendor);if(!normalized)continue;
  const g=groups.get(normalized)||[];g.push({id:String(p.id),title:String(p.title||""),vendor});groups.set(normalized,g);
 }
 const findings:Finding[]=[];
 for(const [normalized,products] of groups){
  const variants=[...new Set(products.map(p=>p.vendor))].sort();
  if(variants.length<2)continue;
  for(const p of products)findings.push({
   productId:p.id,productTitle:p.title,rule:"inconsistent",
   evidence:"Vendor: "+p.vendor,
   detail:"Names representing the same vendor: "+variants.join(" | ")+" (normalized "+normalized+")"
  });
 }
 return finish(rows,findings);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
