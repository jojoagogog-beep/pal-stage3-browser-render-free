import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Product Media Guard","product-media","Find products without media or with just one media item.");
export const rules={issue:{label:"Low product media coverage",priority:"Review",advice:"Review whether additional images or media would be useful."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];
 for(const p of rows){const n=p.media?.nodes?.length||0;if(n<2)findings.push({productId:p.id,productTitle:p.title,rule:"issue",
  evidence:n===0?"No product media":"Only one media item",detail:n===0?"No product media was found.":"The product has just one media item."})}
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
