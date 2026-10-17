import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Product Type Guard","product-type","Find product types that differ only by case, punctuation, or spacing; never modify merchant data.");
export const rules={inconsistent:{label:"Inconsistent product type",priority:"Review",advice:"Review each affected product and choose a canonical product type before making changes."}} as const;
const normalize=(v:string)=>v.normalize("NFKC").trim().toLowerCase().replace(/[\s_\-./,&'’]+/g,"").replace(/[^a-z0-9]+/g,"");
export function auditCatalog(rows:any[]){
 const groups=new Map<string,Array<{id:string;title:string;value:string}>>();
 for(const p of rows){
  const value=String(p.productType||"").trim();if(!value)continue;
  const key=normalize(value);if(!key)continue;
  const list=groups.get(key)||[];list.push({id:String(p.id||""),title:String(p.title||""),value});groups.set(key,list);
 }
 const findings:Finding[]=[];
 for(const [key,list] of groups){
  const observed=[...new Set(list.map(x=>x.value))].sort();
  if(observed.length<2)continue;
  for(const item of list)findings.push({productId:item.id,productTitle:item.title,rule:"inconsistent",evidence:"Product type: "+item.value,detail:"Normalized form: "+key+"; variants: "+observed.join(" | ")});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
