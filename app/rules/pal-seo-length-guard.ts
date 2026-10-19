export const appMeta = {
 shortName:'SEO Length Guard',exportSlug:'seo-length',
 readonlyLabel:'Read-only · SEO quality',eyebrow:'CATALOG QA / SEARCH',
 headline:'Review missing and unusually short or long product SEO metadata.',
 lead:'Check SEO title and description lengths across the current catalog batch without changing products.',
 sidebarHelp:'Choose an SEO metadata issue to review.',
 readOnlyNote:'The audit reads Shopify product data only; it never modifies products.',
 panelTitle:'SEO metadata findings',
 emptyCopy:'No SEO metadata length issues were detected in this batch.'
} as const;
export const rules={
 'missing-seo-title':{label:'SEO title missing',priority:'Review',advice:'Add a meaningful SEO title if needed.'},
 'seo-title-length':{label:'SEO title length',priority:'Review',advice:'Review whether the SEO title works well in search results.'},
 'missing-seo-description':{label:'SEO description missing',priority:'Review',advice:'Add a concise, accurate SEO description where appropriate.'},
 'seo-description-length':{label:'SEO description length',priority:'Review',advice:'Review whether the SEO description conveys the product clearly in search results.'},
} as const;
export type Rule=keyof typeof rules;
export type Product={id:string;title:string;seo?:{title:string|null;description:string|null}|null};
export type Finding={productId:string;productTitle:string;rule:Rule;evidence:string;detail:string};
const norm=(s:string|null|undefined)=>String(s??'').replace(/\s+/g,' ').trim();
export function auditCatalog(products:Product[]){
 const findings:Finding[]=[];
 for(const p of products){
  const title=norm(p.seo?.title),description=norm(p.seo?.description);
  const add=(rule:Rule,detail:string,evidence:string)=>findings.push({productId:p.id,productTitle:p.title,rule,detail,evidence});
  if(!title)add('missing-seo-title','Custom SEO title is not set','(blank)');
  else if(title.length<20||title.length>70)add('seo-title-length',title.length+' characters',title);
  if(!description)add('missing-seo-description','Custom SEO description is not set','(blank)');
  else if(description.length<70||description.length>320)add('seo-description-length',description.length+' characters',description.slice(0,200));
 }
 findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle)||a.rule.localeCompare(b.rule));
 return {products:products.length,findings,skipped:[] as string[]};
}
export function buildCsv(findings:Finding[]){
 const cell=(v:unknown)=>{const x=String(v??'');return '"'+(/^[\s]*[=+@\-\t\r\n]/.test(x)?"'"+x:x).replace(/"/g,'""')+'"';};
 return '\uFEFF'+[['Priority','Product','Product ID','Issue','Evidence','Recommendation'],...findings.map(f=>[rules[f.rule].priority,f.productTitle,f.productId,rules[f.rule].label,f.evidence,rules[f.rule].advice])].map(row=>row.map(cell).join(',')).join('\r\n');
}
