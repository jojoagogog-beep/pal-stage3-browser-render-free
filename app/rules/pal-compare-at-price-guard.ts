import {makeMeta,finish,csvFor,type Finding} from "./pal-paused-audit-core";
export const appMeta=makeMeta("Compare-at Price Guard","compare-at-price",
 "Review variant compare-at prices that are not greater than selling prices, without changing any merchant data.");
export const rules={
 invalid_compare_at:{label:"Compare-at price not above selling price",priority:"Review",
  advice:"Check the intended original price and the current selling price; correct invalid compare-at pricing in Shopify admin."}
} as const;
type Variant={id:string;title:string;price:string;compareAtPrice:string|null};
type Product={id:string;title:string;variants?:{pageInfo?:{hasNextPage:boolean};nodes:Variant[]}};
export function auditCatalog(products:Product[]){
 const findings:Finding[]=[],skipped:string[]=[];
 for(const p of products){
  if(p.variants?.pageInfo?.hasNextPage){
   skipped.push(String(p.title||p.id)+": more than 100 variants; product omitted to prevent incomplete findings");continue;
  }
  for(const v of p.variants?.nodes||[]){
   const sale=Number(v.price),original=v.compareAtPrice===null?NaN:Number(v.compareAtPrice);
   if(!Number.isFinite(sale)||!Number.isFinite(original)||original>sale)continue;
   findings.push({productId:p.id,productTitle:p.title,rule:"invalid_compare_at",
    evidence:"Variant "+v.title+": price "+v.price+" / compare-at "+String(v.compareAtPrice),
    detail:"Compare-at price must exceed the current selling price for valid sale presentation."});
  }
 }
 return finish(products,findings,skipped);
}
export const buildCsv=(findings:Finding[])=>csvFor(findings,rules);
