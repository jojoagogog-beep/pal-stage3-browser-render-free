import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Stale Draft Guard","stale-draft","Identify draft products not updated in at least 90 days.");
export const rules={issue:{label:"Stale draft product",priority:"Review",advice:"Decide whether to update, publish, or archive the draft."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];const now=Date.now();const skipped:string[]=[];
 for(const p of rows){if(p.status!=="DRAFT")continue;const t=Date.parse(String(p.updatedAt||""));
  if(!Number.isFinite(t)){skipped.push(String(p.id||""));continue}
  const days=Math.floor((now-t)/86400000);if(days>=90)findings.push({productId:p.id,productTitle:p.title,rule:"issue",
    evidence:days+" days since update",detail:"Draft has not been updated for "+days+" days."});}
 return finish(rows,findings,skipped);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
