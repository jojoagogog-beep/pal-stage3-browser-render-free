export const appMeta={shortName:"Compare Zero Guard",exportSlug:"compare-zero",readonlyLabel:'Read-only · Catalog QA',eyebrow:'CATALOG QA / REVIEW',headline:"Find zero or negative compare-at prices.",lead:"Find zero or negative compare-at prices.",sidebarHelp:'Focus this review on the flagged catalog pattern.',readOnlyNote:'This app never changes products, variants, tags, prices, or descriptions.',panelTitle:'Catalog findings',emptyCopy:'No matching issues were detected in this product batch.',statusCopy:'Findings are review guidance based on the current product batch.'} as const;
const APP_RULE_LABEL="Invalid compare-at value";
const APP_RULE_ADVICE="Remove or correct zero and negative compare-at prices.";
export type Variant={id:string;title:string;sku:string|null;barcode:string|null;price:string;compareAtPrice:string|null;selectedOptions:Array<{name:string;value:string}>};
export type Product={id:string;title:string;vendor:string;productType:string;tags:string[];handle:string;descriptionHtml:string;variants:{nodes:Variant[]}};
export type Finding={productId:string;productTitle:string;rule:'issue';evidence:string;detail:string};
export type Audit={products:number;findings:Finding[];skipped:string[]};
export const rules={issue:{label:APP_RULE_LABEL,priority:'High',advice:APP_RULE_ADVICE}} as const;
const textOnly=(html:string)=>html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;/gi,' ').replace(/&amp;/gi,'&').replace(/\s+/g,' ').trim();
const normWords=(s:string)=>s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,' ').trim().split(/\s+/).filter(Boolean);
function pushFinding(findings:Finding[],p:Product,evidence:string,detail:string){findings.push({productId:p.id,productTitle:p.title,rule:'issue',evidence,detail})}
function finish(products:Product[],findings:Finding[],skipped:string[]):Audit{findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));return{products:products.length,findings,skipped:[...new Set(skipped)]}}
export function auditCatalog(products:Product[]):Audit{
 const findings:Finding[]=[];const skipped:string[]=[];
 const push=(p:Product,evidence:string,detail:string)=>pushFinding(findings,p,evidence,detail);
 for(const p of products){
    const bad=p.variants.nodes.filter(v=>v.compareAtPrice!=null&&Number(v.compareAtPrice)<=0);if(bad.length)push(p,bad.slice(0,6).map(v=>v.title+': '+v.compareAtPrice).join(', '),'One or more compare-at prices are zero or negative.');
 }
 return finish(products,findings,skipped)
}
export function buildCsv(findings:Finding[]):string{const cell=(v:string)=>'"'+(/^[\s]*[=+@\-\t\r\n]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';return '\ufeff'+[['Priority','Product','Product ID','Issue','Evidence','Recommendation'],...findings.map(f=>['Review',f.productTitle,f.productId,rules.issue.label,f.evidence,rules.issue.advice])].map(r=>r.map(x=>cell(String(x))).join(',')).join('\r\n')}
