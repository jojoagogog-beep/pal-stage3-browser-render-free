import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Option Name Guard","option-name","Review product option names that differ only by case, punctuation, or spacing without modifying store data.");
export const rules={inconsistent:{label:"Inconsistent option name",priority:"Review",advice:"Choose a canonical option name and review impacted products before editing."}} as const;
const normalize=(v:string)=>v.normalize("NFKC").trim().toLowerCase().replace(/[\s_\-./]+/g,"").replace(/[^a-z0-9]+/g,"");
export function auditCatalog(rows:any[]){
 const groups=new Map<string,Array<{id:string;title:string;name:string;position:number|null}>>();
 for(const p of rows){
  for(const opt of p.options||[]){
   const name=String(opt.name||"").trim();if(!name)continue;
   const key=normalize(name);if(!key)continue;
   const list=groups.get(key)||[];list.push({id:String(p.id||""),title:String(p.title||""),name,position:typeof opt.position==="number"?opt.position:null});groups.set(key,list);
  }
 }
 const findings:Finding[]=[];
 for(const [key,list] of groups){
  const observed=[...new Set(list.map(x=>x.name))].sort();
  if(observed.length<2)continue;
  for(const item of list)findings.push({productId:item.id,productTitle:item.title,rule:"inconsistent",evidence:"Option: "+item.name+(item.position!==null?" (#"+item.position+")":""),detail:"Normalized option name: "+key+"; observed: "+observed.join(" | ")});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
