import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Inventory Location Guard","inventory-location","Review differing inventory-location assignments across tracked sibling variants. Read-only.");
export const rules={mixed:{label:"Inconsistent inventory locations",priority:"Review",advice:"Verify intentional warehouse and stock-location differences before modifying inventory assignments."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": additional variants exist");continue}
  const eligible:Array<{id:string;title:string;signature:string}>=[];
  for(const v of variants){
   const item=v.inventoryItem;
   if(!item||item.tracked===undefined){skipped.push(String(p.title||p.id)+": variant inventory tracking unavailable");continue}
   if(!item.tracked)continue;
   const levels=item.inventoryLevels;
   if(!levels?.nodes||levels.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": not all locations available");continue}
   const signature=(levels.nodes||[]).map((x:any)=>String(x.location?.id||"")).filter(Boolean).sort().join("|");
   eligible.push({id:String(v.id||""),title:String(v.title||""),signature});
  }
  if(eligible.length<2||new Set(eligible.map(x=>x.signature)).size<2)continue;
  for(const v of eligible)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"mixed",evidence:"Variant "+v.title+" location IDs: "+(v.signature||"none"),detail:"Tracked variants have different inventory-location assignments"});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
