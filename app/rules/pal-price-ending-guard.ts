export const appMeta = {
  shortName: 'Price Ending Guard',
  exportSlug: 'price-ending',
  readonlyLabel: 'Read-only · Variant prices',
  eyebrow: 'CATALOG QA / PRICE ENDINGS',
  headline: 'Find unusual price endings after bulk edits.',
  lead: 'Profile the price endings used across the current catalog batch and surface rare patterns for human review.',
  sidebarHelp: 'Choose a price-format check.',
  readOnlyNote: 'This app never changes prices.',
  panelTitle: 'Price ending findings',
  emptyCopy: 'No unusual price-ending patterns were found in this batch.',
  statusCopy: 'Price-ending guidance is descriptive catalog QA.'
} as const;

export const rules = {
  'rare-ending': {label:'Rare price ending',priority:'Review',advice:'Confirm whether this ending is intentional or the result of a bulk edit or import.'},
  'mixed-product-endings': {label:'Mixed endings within one product',priority:'Review',advice:'Review whether sibling variants are intended to use different ending patterns.'},
} as const;
export type Rule=keyof typeof rules;
export type Product={id:string;title:string;variants:{nodes:{id:string;title:string;price:string}[]}};
export type Finding={productId:string;productTitle:string;rule:Rule;evidence:string;detail:string};
export type Audit={products:number;findings:Finding[];skipped:string[]};
const ending=(price:string)=>{const n=Number(price);if(!Number.isFinite(n))return null;return Math.round((n-Math.floor(n))*100).toString().padStart(2,'0')};
export function auditCatalog(products:Product[]):Audit{
 const all:{product:Product;variant:{id:string;title:string;price:string};ending:string}[]=[];const counts=new Map<string,number>();
 for(const p of products)for(const v of p.variants?.nodes||[]){const e=ending(v.price);if(e===null)continue;all.push({product:p,variant:v,ending:e});counts.set(e,(counts.get(e)||0)+1);}
 const total=all.length;const dominant=[...counts.entries()].sort((a,b)=>b[1]-a[1])[0];const findings:Finding[]=[];
 if(dominant&&total>=4&&dominant[1]/total>=0.5){
  for(const row of all){
   const c=counts.get(row.ending)||0;
   if(row.ending!==dominant[0]&&(c<=1||c/total<0.15)) findings.push({productId:row.product.id,productTitle:row.product.title,rule:'rare-ending',evidence:row.variant.title+' · '+row.variant.price+' · ending .'+row.ending,detail:'This ending appears '+c+' time(s) in the current batch; dominant ending .'+dominant[0]+' appears '+dominant[1]+' time(s).'});
  }
 }
 for(const p of products){
  const set=new Set((p.variants?.nodes||[]).map(v=>ending(v.price)).filter((x):x is string=>x!==null));
  if(set.size>=3) findings.push({productId:p.id,productTitle:p.title,rule:'mixed-product-endings',evidence:'Observed endings: '+[...set].sort().map(x=>'.'+x).join(', '),detail:'Sibling variants use three or more different cent endings.'});
 }
 findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle)||a.evidence.localeCompare(b.evidence));
 return {products:products.length,findings,skipped:total<4?['At least four variant prices are needed for useful batch-level ending guidance.']:[]};
}
export function buildCsv(findings:Finding[]):string{
 const cell=(v:string)=>'"'+(/^[\s]*[=+@\-\t\r\n]/.test(v)?"'"+v:v).replace(/"/g,'""')+'"';
 return '\ufeff'+[['Priority','Product','Product ID','Issue','Price evidence','Recommendation'],...findings.map(f=>[rules[f.rule].priority,f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])].map(r=>r.map(x=>cell(String(x))).join(',')).join('\r\n');
}
