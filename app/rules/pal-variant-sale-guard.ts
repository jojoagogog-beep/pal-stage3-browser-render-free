import { makeMeta, finish, csvFor, type Finding } from "./pal-paused-audit-core";
export const appMeta=makeMeta("Variant Sale Guard","variant-sale","Audit compare-at prices and inconsistent sale discounts across product variants.");
export const rules={
 invalid_compare_at:{label:"Invalid compare-at price",priority:"High",advice:"Confirm that compare-at is greater than the actual selling price only for an intended sale."},
 partial_sale_mix:{label:"Mixed sale state",priority:"Review",advice:"Confirm whether only some product variants are intended to be on sale."},
 discount_spread:{label:"Discount spread over 15 percentage points",priority:"Review",advice:"Confirm whether differing variant discounts are intentional."},
 zero_price:{label:"Zero-price variant",priority:"Review",advice:"Confirm zero-price variants are intentional and suitable for sale."},
} as const;
export function auditCatalog(rows:any[]){
 const findings:Finding[]=[];
 for(const p of rows){
  const variants=p.variants?.nodes||[];
  const saleDiscounts:number[]=[];
  let sales=0;
  for(const v of variants){
   const price=Number(v.price);const compare=v.compareAtPrice==null?NaN:Number(v.compareAtPrice);
   if(Number.isFinite(price)&&price===0){
     findings.push({productId:p.id,productTitle:p.title,rule:"zero_price",evidence:String(v.title||v.id),detail:"Selling price is zero."});
   }
   if(v.compareAtPrice!=null&&Number.isFinite(compare)){
    if(!Number.isFinite(price)||compare<=price)findings.push({productId:p.id,productTitle:p.title,rule:"invalid_compare_at",evidence:String(v.title||v.id),detail:"Compare-at price is not above the selling price."});
    else{sales++;saleDiscounts.push((compare-price)/compare*100);}
   }
  }
  if(variants.length>1&&sales>0&&sales<variants.length)findings.push({productId:p.id,productTitle:p.title,rule:"partial_sale_mix",evidence:`${sales} / ${variants.length} variants on sale`,detail:"Product variants have mixed sale states."});
  if(saleDiscounts.length>1&&Math.max(...saleDiscounts)-Math.min(...saleDiscounts)>=15)findings.push({productId:p.id,productTitle:p.title,rule:"discount_spread",evidence:`${Math.min(...saleDiscounts).toFixed(1)}%–${Math.max(...saleDiscounts).toFixed(1)}%`,detail:"Variant sale discounts differ by at least 15 percentage points."});
 }
 return finish(rows,findings);
}
export const buildCsv=(f:Finding[])=>csvFor(f,rules);
