import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Empty Collection Guard","empty-collection","Find collections containing no products. Read-only and non-destructive.","collection");
export const rules={empty:{label:"Empty collection",priority:"Review",advice:"Review publication, manual membership, and automated collection rules before editing."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const c of rows){
  if(!c.products||!Array.isArray(c.products.nodes)){skipped.push(String(c.title||c.id)+": collection membership unavailable");continue}
  if(c.products.nodes.length!==0)continue;
  findings.push({productId:String(c.id||""),productTitle:String(c.title||""),rule:"empty",evidence:"Handle: "+String(c.handle||""),detail:"No products are assigned to this collection"});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
