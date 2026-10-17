import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("SKU Format Guard","sku-format","Review SKU formatting drift across variants of a product without changing catalog data.");
export const rules={format:{label:"SKU format inconsistency",priority:"Review",advice:"Confirm casing, separators, and numbering conventions before standardizing product SKUs."}} as const;
function format(sku:string){const parts=sku.trim().split(/[^A-Za-z0-9]+/).filter(Boolean);const casing=/[a-z]/.test(sku)&&/[A-Z]/.test(sku)?"mixed":/[a-z]/.test(sku)?"lower":"upper";const sep=(sku.match(/[^A-Za-z0-9]+/g)||[]).map(x=>/^\s+$/.test(x)?"space":x).join("|")||"none";return casing+";"+sep+";"+parts.length+";"+(parts[0]||"").replace(/[A-Za-z]/g,"A").replace(/[0-9]/g,"9")}
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": more variants to inspect");continue}
  const vs=(p.variants?.nodes||[]).map((v:any)=>({...v,sku:String(v.sku||"").trim()})).filter((v:any)=>v.sku);
  if(vs.length<2)continue;
  const patterns=new Map<string,number>();for(const v of vs){const f=format(v.sku);patterns.set(f,(patterns.get(f)||0)+1)}
  if(patterns.size<2)continue;
  const dominant=[...patterns.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0];
  for(const v of vs){const signature=format(v.sku);if(patterns.size>1)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"format",evidence:"Variant "+String(v.title||"")+": "+v.sku,detail:"Observed "+signature+"; most frequent: "+dominant})}
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
