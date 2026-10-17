import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Customs Data Guard","customs-data","Review shipping-required product variants missing customs tariff or origin information. Read-only, not customs advice.");
export const rules={missing:{label:"Customs data missing",priority:"Review",advice:"Verify the HS code and country of origin against product records before cross-border shipping."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": some variants not loaded");continue}
  for(const v of variants){
   const item=v.inventoryItem;
   if(!item||typeof item.requiresShipping!=="boolean"){skipped.push(String(p.title||p.id)+": shipping state inaccessible");continue}
   if(!item.requiresShipping)continue;
   const hs=String(item.harmonizedSystemCode||"").trim(),origin=String(item.countryCodeOfOrigin||"").trim();
   if(hs&&origin)continue;
   findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"missing",evidence:"Variant "+String(v.title||"")+": HS "+(hs||"missing")+", origin "+(origin||"missing"),detail:!hs&&!origin?"Both HS tariff code and country of origin are absent":!hs?"HS tariff code is absent":"Country of origin is absent"});
  }
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
