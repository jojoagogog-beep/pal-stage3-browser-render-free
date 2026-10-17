import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Option Value Guard","option-value","Find inconsistent variant option values within the same option name, including common size and color aliases.");
export const rules={inconsistent:{label:"Inconsistent option value",priority:"Review",advice:"Review variants sharing the same option and choose a consistent option value; this app never edits store data."}} as const;
const aliases:Record<string,string>={gray:"grey",charcoalgray:"charcoalgrey",xlarge:"xl",extralarge:"xl",xlarg:"xl",xsmall:"xs",extrasmall:"xs",xxlarge:"xxl",extraextralarge:"xxl",xxsmall:"xxs",extraextrasmall:"xxs"};
const normalize=(v:string)=>{const key=v.normalize("NFKC").trim().toLowerCase().replace(/[\s_\-./]+/g,"").replace(/[^a-z0-9]+/g,"");return aliases[key]||key};
export function auditCatalog(rows:any[]){
 const groups=new Map<string,Array<{id:string;title:string;variant:string;value:string;name:string}>>();
 for(const p of rows){
  for(const v of p.variants?.nodes||[]){
   for(const opt of v.selectedOptions||[]){
    const name=String(opt.name||"").trim(),value=String(opt.value||"").trim();
    if(!name||!value)continue;
    const norm=normalize(value);if(!norm)continue;
    const key=name.toLowerCase()+"::"+norm;
    const list=groups.get(key)||[];list.push({id:String(p.id||""),title:String(p.title||""),variant:String(v.title||""),value,name});groups.set(key,list);
   }
  }
 }
 const findings:Finding[]=[];
 for(const [key,list] of groups){
  const observed=[...new Set(list.map(x=>x.value))].sort();
  if(observed.length<2)continue;
  for(const item of list)findings.push({productId:item.id,productTitle:item.title,rule:"inconsistent",evidence:item.name+": "+item.value+" · Variant: "+item.variant,detail:"Same normalized option value ("+key+"), observed: "+observed.join(" | ")});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
