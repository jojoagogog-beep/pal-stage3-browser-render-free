import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";

type Def={name:string;lead:string;collection?:boolean;rules:Record<string,{label:string;priority:"Review"|"High";advice:string}>};
const definitions:Record<string,Def>={
 "pal-collection-rule-guard":{name:"Collection Rule Guard",lead:"Review malformed and duplicated smart-collection rules from live Shopify collection data.",collection:true,rules:{
  empty:{label:"Blank rule condition",priority:"Review",advice:"Review the automated collection's empty rule condition."},
  duplicate:{label:"Duplicate collection rule",priority:"Review",advice:"Remove redundant rules if they were not intentional."}}},
 "pal-rule-drift-guard":{name:"Rule Drift Guard",lead:"Review suspicious smart-collection rule changes and overlapping conditions.",collection:true,rules:{
  empty:{label:"Missing rule value",priority:"Review",advice:"Check whether an empty smart-collection condition is intentional."},
  conflict:{label:"Potential rule conflict",priority:"Review",advice:"Examine conflicting automatic collection constraints."}}},
 "pal-product-image-size-guard":{name:"Product Image Size Guard",lead:"Find undersized images and extreme source-image proportions.",rules:{
  small:{label:"Source image below 800 px",priority:"Review",advice:"Replace with a higher-resolution product image if possible."},
  unusual:{label:"Unusual source-image ratio",priority:"Review",advice:"Check cropping and rendering at storefront breakpoints."}}},
 "pal-product-tag-count-guard":{name:"Product Tag Count Guard",lead:"Identify products with no tags or unusually large tag inventories.",rules:{
  none:{label:"No product tags",priority:"Review",advice:"Add tags if useful for merchandising and filter operations."},
  many:{label:"More than 20 product tags",priority:"Review",advice:"Review redundant and obsolete tags."}}},
 "pal-product-handle-guard":{name:"Product Handle Guard",lead:"Review excessive URL handle length and malformed hyphen patterns.",rules:{
  long:{label:"Long product URL handle",priority:"Review",advice:"Consider a concise, descriptive canonical handle."},
  pattern:{label:"Unusual handle pattern",priority:"Review",advice:"Review repeated or leading/trailing hyphens."}}},
 "pal-product-image-aspect-guard":{name:"Product Image Aspect Guard",lead:"Find inconsistent image aspect ratios within an individual product.",rules:{
  aspect:{label:"Inconsistent image aspect ratios",priority:"Review",advice:"Review image crops for consistency across the product gallery."}}},
 "pal-archived-stock-guard":{name:"Archived Stock Guard",lead:"Identify archived products whose tracked variants still report positive available inventory.",rules:{
  archived:{label:"Archived product with stock",priority:"Review",advice:"Verify that archived stock is intentionally retained and not abandoned."}}},
 "pal-negative-inventory-guard":{name:"Negative Inventory Guard",lead:"Identify tracked variants with negative aggregate inventory quantities.",rules:{
  negative:{label:"Negative tracked inventory",priority:"High",advice:"Reconcile inventory levels and shipping allocations before editing."}}},
 "pal-variant-count-guard":{name:"Variant Count Guard",lead:"Flag products with more than 50 variants in the scanned batch.",rules:{
  many:{label:"High variant count",priority:"Review",advice:"Review product complexity and storefront options."}}},
 "pal-draft-stock-guard":{name:"Draft Stock Guard",lead:"Identify draft products that still carry positive tracked inventory.",rules:{
  draft:{label:"Draft product with positive stock",priority:"Review",advice:"Verify the inventory is intentional and ready for catalog publication."}}},
 "pal-option-complexity-guard":{name:"Option Complexity Guard",lead:"Identify products with large variant and option combinations.",rules:{
  complexity:{label:"High option or variant complexity",priority:"Review",advice:"Simplify option structure when possible and review user experience."}}},
 "pal-seo-duplicate-guard":{name:"SEO Duplicate Guard",lead:"Find duplicate custom SEO titles and descriptions within the current product batch.",rules:{
  title:{label:"Repeated custom SEO title",priority:"Review",advice:"Give affected pages specific, distinct SEO titles."},
  description:{label:"Repeated custom SEO description",priority:"Review",advice:"Review and customize repeated search snippets."}}},
 "pal-description-html-guard":{name:"Description HTML Guard",lead:"Flag potentially problematic or heavy description markup.",rules:{
  empty:{label:"Missing visible description content",priority:"Review",advice:"Add a useful merchant-facing description."},
  length:{label:"Large description HTML",priority:"Review",advice:"Trim unnecessary markup while preserving formatting."},
  tags:{label:"Heavy HTML markup",priority:"Review",advice:"Simplify unnecessary markup and nested elements."},
  styles:{label:"Excessive inline styles",priority:"Review",advice:"Reduce inline styling for storefront compatibility."},
  breaks:{label:"Excessive line-break tags",priority:"Review",advice:"Use semantic paragraphs and headings instead of repeated breaks."},
  active:{label:"Embedded active HTML content",priority:"High",advice:"Review scripts, iframes and embedded active elements for safety."}}},
 "pal-duplicate-description-guard":{name:"Duplicate Description Guard",lead:"Find repeated normalized product descriptions across the current catalog batch.",rules:{
  duplicate:{label:"Duplicate product description",priority:"Review",advice:"Personalize repeated descriptions for clarity and search differentiation."}}}
};
const plain=(v:unknown)=>String(v??"").replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi," ")
 .replace(/<[^>]*>/g," ").replace(/&nbsp;|&#160;/gi," ").replace(/&amp;/gi,"&").replace(/\s+/g," ").trim();
const norm=(v:unknown)=>plain(v).normalize("NFKC").toLowerCase();
const stringify=(v:unknown)=>String(v??"");
function buildAudit(slug:string,rows:any[]):{products:number;findings:Finding[];skipped:string[]}{
 const f:Finding[]=[],skipped:string[]=[];
 const add=(p:any,rule:string,evidence:string,detail:string)=>{
   f.push({productId:stringify(p.id),productTitle:stringify(p.title),rule,evidence,detail});
 };
 const def=definitions[slug];
 if(!def)throw new Error("Unsupported review rule");
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  if(["pal-archived-stock-guard","pal-negative-inventory-guard","pal-draft-stock-guard","pal-variant-count-guard","pal-option-complexity-guard"].includes(slug)&&p.variants?.pageInfo?.hasNextPage){
    skipped.push(stringify(p.title||p.id)+": only the first variants were scanned");
  }
  switch(slug){
   case "pal-collection-rule-guard":{
    const rules=p.ruleSet?.rules;
    if(!Array.isArray(rules))break;
    const seen=new Set<string>();
    for(const r of rules){
      const condition=stringify(r.condition).trim();
      if(!condition)add(p,"empty",stringify(r.column)+" / "+stringify(r.relation),"Empty rule condition");
      const key=[r.column,r.relation,condition].join(":").toLowerCase();
      if(seen.has(key))add(p,"duplicate",key,"Duplicate smart collection constraint");
      seen.add(key);
    }
    break;
   }
   case "pal-rule-drift-guard":{
    const rules=p.ruleSet?.rules;
    if(!Array.isArray(rules))break;
    const fields=new Map<string,Set<string>>();
    for(const r of rules){
      const condition=stringify(r.condition).trim();
      if(!condition)add(p,"empty",stringify(r.column)+"/"+stringify(r.relation),"Condition has no value");
      const k=stringify(r.column)+":"+stringify(r.relation);
      let values=fields.get(k);if(!values){values=new Set();fields.set(k,values)}
      values.add(condition.toLowerCase());
    }
    for(const [field,values] of fields)if(values.size>1&&!p.ruleSet?.appliedDisjunctively)
      add(p,"conflict",field,values.size+" different conjunction values; verify overlap in the catalog");
    break;
   }
   case "pal-product-image-size-guard":{
    for(const i of p.images?.nodes||[]){
      const w=Number(i.width),h=Number(i.height);
      if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)continue;
      if(w<800||h<800){add(p,"small",w+" × "+h+" px","Small source image");break;}
      const ratio=w/h;
      if(ratio>2||ratio<0.5){add(p,"unusual",ratio.toFixed(2)+":1","Unusual image proportions");break;}
    }
    break;
   }
   case "pal-product-tag-count-guard":{
    const n=Array.isArray(p.tags)?p.tags.length:0;
    if(n===0)add(p,"none","0 tags","No product tags");
    if(n>20)add(p,"many",n+" tags","Large tag inventory");
    break;
   }
   case "pal-product-handle-guard":{
    const h=stringify(p.handle);
    if(h.length>60)add(p,"long",h.length+" characters","Long URL handle");
    if(h.includes("--")||h.startsWith("-")||h.endsWith("-"))
      add(p,"pattern",h.slice(0,140),"Unexpected hyphen pattern");
    break;
   }
   case "pal-product-image-aspect-guard":{
    const ratios=(p.images?.nodes||[]).filter((i:any)=>Number(i.width)>0&&Number(i.height)>0)
      .map((i:any)=>Number(i.width)/Number(i.height));
    if(ratios.length>=2){
      const lo=Math.min(...ratios),hi=Math.max(...ratios);
      if(lo>0&&hi/lo>=1.6)add(p,"aspect",lo.toFixed(2)+":1 – "+hi.toFixed(2)+":1","Images have mixed aspect ratios");
    }
    break;
   }
   case "pal-archived-stock-guard":
   case "pal-draft-stock-guard":
   case "pal-negative-inventory-guard":{
    if(p.variants?.pageInfo?.hasNextPage)break;
    for(const v of variants){
      const q=Number(v.inventoryQuantity);
      if(v.inventoryItem?.tracked!==true||!Number.isSafeInteger(q))continue;
      if(slug==="pal-negative-inventory-guard"&&q<0)add(p,"negative",stringify(v.title)+": "+q+" units","Tracked variant inventory below zero");
      if(slug==="pal-archived-stock-guard"&&p.status==="ARCHIVED"&&q>0)add(p,"archived",stringify(v.title)+": "+q+" units","Archived product with positive inventory");
      if(slug==="pal-draft-stock-guard"&&p.status==="DRAFT"&&q>0)add(p,"draft",stringify(v.title)+": "+q+" units","Draft product with positive inventory");
    }
    break;
   }
   case "pal-variant-count-guard":{
    const count=variants.length;
    if(count>50)add(p,"many",count+(p.variants?.pageInfo?.hasNextPage?"+":"")+" variants","Exceeds the 50-variant review threshold");
    break;
   }
   case "pal-option-complexity-guard":{
    const count=variants.length,optionCount=Array.isArray(p.options)?p.options.length:0;
    if(count>50)add(p,"complexity",count+" variants · "+optionCount+" options","High option/variant complexity");
    break;
   }
   case "pal-description-html-guard":{
    const html=stringify(p.descriptionHtml);
    const tags=(html.match(/<[^>]+>/g)||[]).length;
    const styles=(html.match(/style\s*=/gi)||[]).length;
    const scripts=(html.match(/<(script|iframe|object|embed)\b/gi)||[]).length;
    const breaks=(html.match(/<br\s*\/?\s*>/gi)||[]).length;
    if(!plain(html))add(p,"empty","Empty description","No visible description content");
    if(html.length>12000)add(p,"length",html.length+" HTML chars","Large HTML description");
    if(tags>120)add(p,"tags",tags+" HTML elements","Heavy markup");
    if(styles>12)add(p,"styles",styles+" inline styles","Excess inline styling");
    if(breaks>25)add(p,"breaks",breaks+" line breaks","Repeated BR tags");
    if(scripts>0)add(p,"active",scripts+" active elements","Embedded active HTML content");
    break;
   }
  }
 }
 if(slug==="pal-seo-duplicate-guard"){
  for(const [field,rule] of [["title","title"],["description","description"]] as const){
    const groups=new Map<string,any[]>();
    for(const p of rows){
      const v=norm(p.seo?.[field]);if(!v)continue;
      const a=groups.get(v)||[];a.push(p);groups.set(v,a);
    }
    for(const group of groups.values())if(group.length>1)for(const p of group)
      add(p,rule,group.length+" products share the same SEO "+field,"Repeated custom SEO "+field);
  }
 }
 if(slug==="pal-duplicate-description-guard"){
  const groups=new Map<string,any[]>();
  for(const p of rows){
    const key=norm(p.descriptionHtml);if(key.length<40)continue;
    const g=groups.get(key)||[];g.push(p);groups.set(key,g);
  }
  for(const group of groups.values())if(group.length>1)for(const p of group)
    add(p,"duplicate",group.length+" products share identical normalized content","Duplicated description in the scanned batch");
 }
 return finish(rows,f,skipped);
}
function makeExtension(slug:string){
 const def=definitions[slug];
 const appMeta=makeMeta(def.name,slug.replace(/^pal-/,""),def.lead,def.collection?"collection":"product");
 const rules=def.rules;
 return {appMeta,rules,auditCatalog:(rows:any[])=>buildAudit(slug,rows),buildCsv:(f:Finding[])=>csvFor(f,rules)};
}
export const extraReviewRules={
 "pal-collection-rule-guard":makeExtension("pal-collection-rule-guard"),
 "pal-rule-drift-guard":makeExtension("pal-rule-drift-guard"),
 "pal-product-image-size-guard":makeExtension("pal-product-image-size-guard"),
 "pal-product-tag-count-guard":makeExtension("pal-product-tag-count-guard"),
 "pal-product-handle-guard":makeExtension("pal-product-handle-guard"),
 "pal-product-image-aspect-guard":makeExtension("pal-product-image-aspect-guard"),
 "pal-archived-stock-guard":makeExtension("pal-archived-stock-guard"),
 "pal-negative-inventory-guard":makeExtension("pal-negative-inventory-guard"),
 "pal-variant-count-guard":makeExtension("pal-variant-count-guard"),
 "pal-draft-stock-guard":makeExtension("pal-draft-stock-guard"),
 "pal-option-complexity-guard":makeExtension("pal-option-complexity-guard"),
 "pal-seo-duplicate-guard":makeExtension("pal-seo-duplicate-guard"),
 "pal-description-html-guard":makeExtension("pal-description-html-guard"),
 "pal-duplicate-description-guard":makeExtension("pal-duplicate-description-guard")
} as const;
