export const appMeta={
 shortName:"Shipping Weight Guard",
 exportSlug:"shipping-weight",
 readonlyLabel:"Read-only · Shipping data QA",
 eyebrow:"CATALOG QA / SHIPPING",
 headline:"Shipping Weight Guard",
 lead:"Find missing, zero, and unusually inconsistent shipping weights for your product variants.",
 sidebarHelp:"Review variants and correct weights where appropriate before relying on weight-based rates.",
 readOnlyNote:"This audit never modifies product data.",
 panelTitle:"Shipping weight findings",
 emptyCopy:"No missing, zero, or unusually inconsistent shipping weights were found in this catalog batch.",
 entityKind:"product"
} as const;
export const rules={
 missing_weight:{label:"Shipping variant has no readable weight",priority:"High",advice:"Set a correct shipping weight for the variant."},
 zero_weight:{label:"Shipping variant has zero or negative weight",priority:"High",advice:"Confirm the correct weight before applying weight-based shipping rates."},
 mixed_weight_completeness:{label:"Sibling shipping variants mix valid and missing weights",priority:"Medium",advice:"Review the weights for all sibling variants together."},
 weight_outlier:{label:"Shipping weight differs at least 5× from sibling median",priority:"Review",advice:"Verify the weight and units for this variant."}
};
type Finding={productId:string;productTitle:string;rule:keyof typeof rules;evidence:string;detail:string};
const toGrams=(w:any):number|null=>{
 if(!w||!Number.isFinite(Number(w.value)))return null;
 const v=Number(w.value);
 switch(String(w.unit||"").toUpperCase()){
 case "GRAMS":return v;case "KILOGRAMS":return v*1000;case "OUNCES":return v*28.349523125;case "POUNDS":return v*453.59237;default:return null;
 }
};
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];
 const skipped:string[]=[];
 for(const p of rows){
  const variants=(p.variants?.nodes||[]).filter((v:any)=>v.inventoryItem?.requiresShipping);
  const data=variants.map((v:any)=>({title:String(v.title||""),grams:toGrams(v.inventoryItem?.measurement?.weight)}));
  const positive=data.filter((x:any)=>(x.grams??0)>0).map((x:any)=>x.grams as number).sort((a:number,b:number)=>a-b);
  const m=positive.length;const median=m?(m%2?positive[Math.floor(m/2)]:(positive[m/2-1]+positive[m/2])/2):0;
  let missing=0,valid=0;
  for(const x of data){
   const grams=x.grams;
   const evidence=x.title+" — "+(grams===null?"no valid weight":grams.toFixed(3)+" g");
   if(grams===null){missing++;findings.push({productId:p.id,productTitle:p.title,rule:"missing_weight",evidence,detail:"Shipping variant "+x.title+" has no readable weight."});continue;}
   if(grams<=0){missing++;findings.push({productId:p.id,productTitle:p.title,rule:"zero_weight",evidence,detail:"Shipping variant "+x.title+" has zero or negative weight."});continue;}
   valid++;
   if(m>=3&&median>0&&Math.max(grams/median,median/grams)>=5)findings.push({productId:p.id,productTitle:p.title,rule:"weight_outlier",evidence,detail:"Variant "+x.title+" weighs at least 5× the sibling median."});
  }
  if(valid>0&&missing>0)findings.push({productId:p.id,productTitle:p.title,rule:"mixed_weight_completeness",evidence:valid+" valid, "+missing+" missing/zero shipping weights",detail:"Review all shipping variants for this product."});
  if((p.variants?.nodes||[]).length===100)skipped.push(String(p.title)+" (more than 100 variants)");
 }
 return {products:rows.length,findings,skipped};
}
export function buildCsv(findings:Finding[]){
 const safe=(v:string)=>'"'+(/^\s*[=+@\-\t\r\n]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';
 const rows=[["Product","Product ID","Issue","Evidence","Recommended action"],...findings.map(f=>[f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])];
 return "\uFEFF"+rows.map(row=>row.map(x=>safe(String(x))).join(",")).join("\r\n");
}
