import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Selling Plan Guard","selling-plan","Find product variants with different subscription or selling-plan group assignments. Read-only.");
export const rules={mixed:{label:"Inconsistent selling-plan coverage",priority:"Review",advice:"Confirm whether individual variants intentionally have different subscription or purchase options before changing them."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": additional variants not audited");continue}
  const groups:Array<{v:any;signature:string}>=[];
  let invalid=false;
  for(const v of variants){
   if(!v.sellingPlanGroups?.nodes||v.sellingPlanGroups.pageInfo?.hasNextPage){invalid=true;break}
   const signature=v.sellingPlanGroups.nodes.map((g:any)=>String(g.id||"")).sort().join("|");
   groups.push({v,signature});
  }
  if(invalid){skipped.push(String(p.title||p.id)+": selling-plan groups not fully read");continue}
  if(groups.length<2||new Set(groups.map(x=>x.signature)).size<2)continue;
  for(const x of groups)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"mixed",evidence:"Variant "+String(x.v.title||"")+" selling-plan group IDs: "+(x.signature||"none"),detail:"Sibling variants have different selling-plan groups"});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
