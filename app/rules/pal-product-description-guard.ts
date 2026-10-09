import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Product Description Guard","product-description","Flag products with missing or very short descriptions.");
export const rules={issue:{label:"Missing or short description",priority:"Review",advice:"Review the product description for clarity and completeness."}} as const;
function plaintext(s:string){return s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi," ").replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi," ").replace(/<[^>]+>/g," ").replace(/&nbsp;|&#160;/gi," ").replace(/&amp;/gi,"&").replace(/\s+/g," ").trim()}
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];
 for(const p of rows){const n=plaintext(String(p.descriptionHtml||"")).length;if(n<80)findings.push({productId:p.id,productTitle:p.title,rule:"issue",
   evidence:n+" text characters",detail:n===0?"Description has no visible text.":"Description has fewer than 80 text characters."});}
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
