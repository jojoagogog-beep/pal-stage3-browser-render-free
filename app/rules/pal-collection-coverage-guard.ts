import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Collection Coverage Guard","collection-coverage","Find products that have not been assigned to any collection, without editing membership.");
export const rules={orphaned:{label:"Product without collection",priority:"Review",advice:"Confirm whether the product should appear in a collection; review collections before assigning it."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  if(!p.collections?.nodes){skipped.push(String(p.title||p.id)+": collections could not be read");continue}
  if(p.collections.nodes.length)continue;
  findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"orphaned",evidence:"Status: "+String(p.status||"unknown"),detail:"No collection associations were found"});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
