import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Tag Consistency Guard","tag-consistency","Review tags differing only by capitalization, spacing or punctuation without editing merchant data.");
export const rules={inconsistent:{label:"Inconsistent tag spelling",priority:"Review",advice:"Review the affected products and standardize tag spellings in the Shopify admin."}} as const;
const normalize=(v:string)=>v.normalize("NFKC").trim().toLowerCase().replace(/[\s_\-./,&'’]+/g,"").replace(/[^\p{L}\p{N}]+/gu,"");
export function auditCatalog(rows:any[]){
  const groups=new Map<string,Array<{id:string;title:string;tag:string}>>();
  for(const p of rows){
    for(const original of Array.isArray(p.tags)?p.tags:[]){
      const tag=String(original||"").trim();if(!tag)continue;
      const key=normalize(tag);if(!key)continue;
      const members=groups.get(key)||[];
      members.push({id:String(p.id||""),title:String(p.title||""),tag});
      groups.set(key,members);
    }
  }
  const findings:Finding[]=[];
  for(const [key,members] of groups){
    const observed=[...new Set(members.map(x=>x.tag))].sort();
    if(observed.length<2)continue;
    const detail="Normalized form: "+key+"; observed tags: "+observed.join(" | ");
    for(const m of members)findings.push({productId:m.id,productTitle:m.title,rule:"inconsistent",evidence:"Tag: "+m.tag,detail});
  }
  return finish(rows,findings);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
