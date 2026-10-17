import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Unit Cost Guard","unit-cost","Review variants without recorded unit cost. Shopify's View product costs permission is required to view these values.");
export const rules={missing:{label:"Missing unit cost",priority:"Review",advice:"Verify your permissions and record product acquisition cost if applicable; never enter an estimated cost automatically."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": more variants not loaded");continue}
  for(const v of variants){
   if(!v.inventoryItem){skipped.push(String(p.title||p.id)+": inventory record unavailable");continue}
   if(v.inventoryItem.unitCost!==null&&v.inventoryItem.unitCost!==undefined)continue;
   findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"missing",evidence:"Variant "+String(v.title||"")+" SKU "+String(v.sku||""),detail:"Unit cost is unavailable or not recorded; check permission to view product costs before concluding it is missing"});
  }
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
