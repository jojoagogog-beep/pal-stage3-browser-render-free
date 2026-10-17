import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Variant Tax Flag Guard","variant-tax-flag","Flag mixed taxable settings across sibling variants. Read-only diagnostics, not tax advice.");
export const rules={mixed:{label:"Mixed variant taxable flags",priority:"Review",advice:"Check variant taxable settings against applicable requirements before making any edits."}} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(p.variants?.pageInfo?.hasNextPage){skipped.push(String(p.title||p.id)+": some variants not loaded");continue}
  const yes=variants.filter((v:any)=>v.taxable===true).length;
  const no=variants.filter((v:any)=>v.taxable===false).length;
  if(!yes||!no)continue;
  for(const v of variants)findings.push({productId:String(p.id||""),productTitle:String(p.title||""),rule:"mixed",evidence:String(v.title||"")+": taxable="+String(v.taxable),detail:yes+" taxable; "+no+" not taxable. Diagnostic only."});
 }
 return finish(rows,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
