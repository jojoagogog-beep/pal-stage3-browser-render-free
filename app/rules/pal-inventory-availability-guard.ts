import {auditCatalog as auditInventory,ISSUE_DEFINITIONS,type ProductInput,type IssueKey} from "./inventory-availability-engine";
export const appMeta={
 shortName:"Inventory Availability Guard",
 exportSlug:"inventory-avail",
 readonlyLabel:"Read-only · Inventory data QA",
 eyebrow:"INVENTORY QA / REVIEW",
 headline:"Inventory Availability Guard",
 lead:"Review inventory tracking, per-location availability and inconsistent stock policies.",
 sidebarHelp:"Inspect tracked variants and inconsistent availability before updating stock records.",
 readOnlyNote:"This audit never modifies inventory or merchant data.",
 panelTitle:"Inventory availability findings",
 emptyCopy:"No inventory tracking or availability mismatches found in this catalog batch.",
 entityKind:"product"
} as const;
export const rules=Object.fromEntries(Object.entries(ISSUE_DEFINITIONS).map(([k,v])=>[k,{label:v.label,priority:v.priority,advice:v.recommendation}])) as Record<IssueKey,{label:string;priority:string;advice:string}>;
type Finding={productId:string;productTitle:string;rule:IssueKey;evidence:string;detail:string};
export function auditCatalog(rows:any[]){
 const normalized:ProductInput[]=rows.map((p:any)=>({
  id:String(p.id),legacyResourceId:String(p.legacyResourceId||p.id).split("/").pop()||"",
  title:String(p.title||""),status:String(p.status||""),
  variantsLimited:!!p.variants?.pageInfo?.hasNextPage,
  variants:(p.variants?.nodes||[]).map((v:any)=>({
   id:String(v.id),legacyResourceId:String(v.legacyResourceId||v.id).split("/").pop()||"",
   title:String(v.title||""),inventoryPolicy:v.inventoryPolicy==="CONTINUE"?"CONTINUE":"DENY",
   inventoryQuantity:Number(v.inventoryQuantity||0),
   tracked:Boolean(v.inventoryItem?.tracked),
   inventoryLevelsLimited:!!v.inventoryItem?.inventoryLevels?.pageInfo?.hasNextPage,
   inventoryLevels:(v.inventoryItem?.inventoryLevels?.nodes||[]).map((l:any)=>({
    available:Number((l.quantities||[]).find((q:any)=>q.name==="available")?.quantity||0)
   }))
  }))
 }));
 const x=auditInventory(normalized);const findings:Finding[]=[];
 for(const p of x.products){
  for(const key of p.issueKeys){
   const issues=p.variants.filter(v=>v.issueKeys.includes(key));
   findings.push({
    productId:p.id,productTitle:p.title,rule:key,
    evidence:issues.length?issues.map(v=>v.title).slice(0,8).join(", "):p.findings.join("; ").slice(0,300),
    detail:p.findings.join("; ").slice(0,700)||rules[key].label
   });
  }
 }
 const skipped=x.products.flatMap(p=>[
  ...(p.variantsLimited?[p.title+" (more than 100 variants)"]:[]),
  ...p.variants.filter(v=>v.inventoryLevelsLimited).map(v=>p.title+" / "+v.title+" (more than 100 inventory levels)")
 ]);
 return {products:rows.length,findings,skipped};
}
export function buildCsv(findings:Finding[]){
 const safe=(v:string)=>'"'+(/^\s*[=+@\-\t\r\n]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';
 const rows=[["Product","Product ID","Issue","Evidence","Recommended action"],...findings.map(f=>[f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])];
 return "\uFEFF"+rows.map(row=>row.map(v=>safe(String(v))).join(",")).join("\r\n");
}
