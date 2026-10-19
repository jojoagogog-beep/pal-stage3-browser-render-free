export const appMeta = {
  shortName: 'Product Title Guard', exportSlug: 'product-title',
  readonlyLabel: 'Read-only · Catalog QA', eyebrow: 'CATALOG QA / TITLES',
  headline: 'Review short, long, uppercase and repeated product titles.',
  lead: 'Check product-title quality and normalized duplicates in the current catalog batch without modifying merchant products.',
  sidebarHelp: 'Choose a title-quality issue to review.',
  readOnlyNote: 'This audit only reads titles; it never changes products.',
  panelTitle: 'Product title findings',
  emptyCopy: 'No product-title issues were detected in this batch.',
} as const;
export const rules = {
  'short-title': { label: 'Short title', priority: 'Review', advice: 'Add accurate details to make this title informative, where appropriate.' },
  'long-title': { label: 'Long title', priority: 'Review', advice: 'Shorten excessive title text while preserving meaningful product details.' },
  'all-caps': { label: 'All-uppercase title', priority: 'Review', advice: 'Use readable capitalization unless the uppercase naming is intentional.' },
  'duplicate-normalized-title': { label: 'Duplicate normalized title', priority: 'Review', advice: 'Confirm if multiple products should use the same normalized name.' },
} as const;
export type Rule=keyof typeof rules;
export type Product={id:string;title:string};
export type Finding={productId:string;productTitle:string;rule:Rule;evidence:string;detail:string};
const norm=(s:string)=>s.trim().toLowerCase().replace(/\s+/g,' ');
export function auditCatalog(products:Product[]){
 const findings:Finding[]=[];
 const counts=new Map<string,number>();
 for(const p of products) counts.set(norm(p.title),(counts.get(norm(p.title))||0)+1);
 for(const p of products){
  const t=p.title.trim(),letters=t.replace(/[^A-Za-z]/g,'');
  let rule:Rule|null=null, detail='';
  if(t.length<10){rule='short-title';detail=t.length+' characters';}
  else if(t.length>80){rule='long-title';detail=t.length+' characters';}
  else if(letters.length>=5&&letters===letters.toUpperCase()){rule='all-caps';detail='Review title casing';}
  else if((counts.get(norm(t))||0)>1){rule='duplicate-normalized-title';detail='Another product in the current batch uses the same normalized title';}
  if(rule) findings.push({productId:p.id,productTitle:p.title,rule,evidence:p.title,detail});
 }
 findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));
 return {products:products.length,findings,skipped:[] as string[]};
}
export function buildCsv(findings:Finding[]){
 const cell=(v:unknown)=>{const x=String(v??'');return '"'+(/^[\s]*[=+@\-\t\r\n]/.test(x)?"'"+x:x).replace(/"/g,'""')+'"';};
 return '\uFEFF'+[['Priority','Product','Product ID','Issue','Evidence','Recommendation'],...findings.map(f=>[rules[f.rule].priority,f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])].map(row=>row.map(cell).join(',')).join('\r\n');
}
