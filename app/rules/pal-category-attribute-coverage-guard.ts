import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Category Attribute Guard","category-attribute","Audit product taxonomy categories and missing category-specific attributes.");
export const rules={
 no_category:{label:"Missing product category",priority:"Review",advice:"Assign an appropriate Shopify taxonomy category."},
 issue:{label:"Missing category-specific attribute",priority:"Review",advice:"Review the applicable category fields and populate missing values when appropriate."}
} as const;
export type Definition={id:string;namespace:string;key:string;name:string;categoryValues:string[]};
export function auditCatalog(rows:any[],definitions:Definition[]=[]){
 const findings:Finding[]=[];
 for(const p of rows){
  const cat=p.category?.id?.split("/").pop();
  if(!cat){findings.push({productId:p.id,productTitle:p.title,rule:"no_category",evidence:"No taxonomy category assigned",detail:"The product has no category."});continue}
  const applicable=definitions.filter(d=>d.categoryValues.includes(cat));
  const fields=p.metafields?.nodes||[];
  const missing=applicable.filter(d=>{const value=fields.find((f:any)=>f.namespace===d.namespace&&f.key===d.key)?.value;return value==null||!String(value).trim()||String(value).trim()==="[]";});
  if(missing.length)findings.push({productId:p.id,productTitle:p.title,rule:"issue",
   evidence:missing.slice(0,8).map(d=>d.name).join(", "),detail:missing.length+" applicable category-specific attributes missing."});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
