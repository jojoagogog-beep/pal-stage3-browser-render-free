import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Product Template Guard","product-template","Find unusual product template assignments for manual review.");
export const rules={issue:{label:"Template assignment anomaly",priority:"Review",advice:"Check whether this product's template assignment is intentional."}} as const;
const norm=(s:unknown)=>String(s||"").trim().toLowerCase().replace(/\s+/g," ");
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];const counts=new Map<string,number>();const groups=new Map<string,any[]>();
 for(const p of rows){const t=norm(p.templateSuffix)||"default";counts.set(t,(counts.get(t)||0)+1);
  const g=norm(p.vendor)+"|"+norm(p.productType);if(g!=="|")groups.set(g,[...(groups.get(g)||[]),p]);}
 for(const p of rows){const t=norm(p.templateSuffix)||"default";const reasons:string[]=[];
  if(t!=="default"&&/(^|[-_.])(test|draft|old|copy|backup|temp)([-_.]|$)/i.test(t))reasons.push("Potential legacy template name");
  if(t!=="default"&&counts.get(t)===1)reasons.push("One-off template in this batch");
  const peers=groups.get(norm(p.vendor)+"|"+norm(p.productType))||[];
  if(peers.length>=3){const peerCounts=new Map<string,number>();for(const peer of peers){const x=norm(peer.templateSuffix)||"default";peerCounts.set(x,(peerCounts.get(x)||0)+1)}
   const [common,n]=[...peerCounts].sort((a,b)=>b[1]-a[1])[0]||["default",0];if(n>=2&&t!==common)reasons.push("Different from comparable products in this batch");}
  if(reasons.length)findings.push({productId:p.id,productTitle:p.title,rule:"issue",evidence:"Template: "+t,detail:reasons.join("; ")});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
