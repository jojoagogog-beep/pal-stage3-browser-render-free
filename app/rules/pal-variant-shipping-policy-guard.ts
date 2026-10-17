import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Variant Shipping Guard","variant-shipping","Review inconsistent shipping, weight and tracking requirements among sibling variants. Read-only.");
export const rules={shipping:{label:"Mixed shipping requirements",priority:"Review",advice:"Verify whether sibling variants are intentionally physical or digital."},weight:{label:"Missing physical shipping weight",priority:"Review",advice:"Set an accurate shipment weight where shipping is required."},tracking:{label:"Mixed inventory tracking",priority:"Review",advice:"Check whether sibling variants intentionally differ in inventory tracking."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const vs=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": additional variants not checked");continue}
  const data=vs.map((v:any)=>({v,shipping:v.inventoryItem?.requiresShipping,tracking:v.inventoryItem?.tracked,weight:v.inventoryItem?.measurement?.weight?.value}));
  if(data.some((x:any)=>typeof x.shipping!=="boolean"||typeof x.tracking!=="boolean")){skipped.push(String(p.title||p.id)+": unavailable shipping or tracking information");continue}
  const mixedShipping=new Set(data.map((x:any)=>x.shipping)).size>1,mixedTracking=new Set(data.map((x:any)=>x.tracking)).size>1;
  for(const x of data){
   const ev="Variant "+String(x.v.title||"")+" requires shipping: "+String(x.shipping);
   if(mixedShipping)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"shipping",evidence:ev,detail:"Some sibling variants require shipping while others do not"});
   if(x.shipping&&(x.weight===null||x.weight===undefined||Number(x.weight)<=0))findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"weight",evidence:ev,detail:"No positive weight recorded for shipping-required variant"});
   if(mixedTracking)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"tracking",evidence:"Variant "+String(x.v.title||"")+" tracked: "+String(x.tracking),detail:"Inventory tracking differs between sibling variants"});
  }
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
