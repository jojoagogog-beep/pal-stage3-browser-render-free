import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Inventory Policy Guard","inventory-policy","Review products whose variants have inconsistent overselling policies. The app never changes store data.");
export const rules={mixed:{label:"Mixed inventory policies",priority:"Review",advice:"Check whether sibling variants are intentionally configured with different overselling policies."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const nodes=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": not all variants loaded");continue}
  const continued=nodes.filter((v:any)=>v.inventoryPolicy==="CONTINUE").length;
  const denied=nodes.filter((v:any)=>v.inventoryPolicy==="DENY").length;
  if(!continued||!denied)continue;
  for(const v of nodes)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"mixed",evidence:String(v.title||"")+": "+String(v.inventoryPolicy||""),detail:continued+" continue selling; "+denied+" deny overselling"});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
