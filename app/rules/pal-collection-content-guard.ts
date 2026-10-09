import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Collection Content Guard","collection-content","Review collections with missing descriptions, images, or SEO fields.","collection");
export const rules={issue:{label:"Missing collection content",priority:"Review",advice:"Review and complete missing collection content where appropriate."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];
 for(const c of rows){const missing:string[]=[];
  if(!String(c.description||"").trim())missing.push("Description");
  if(!c.image?.url)missing.push("Image");
  if(!String(c.seo?.title||"").trim())missing.push("SEO title");
  if(!String(c.seo?.description||"").trim())missing.push("SEO description");
  if(missing.length)findings.push({productId:c.id,productTitle:c.title,rule:"issue",evidence:missing.join(", "),
   detail:"Missing "+missing.length+" collection content field(s)."});}
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
