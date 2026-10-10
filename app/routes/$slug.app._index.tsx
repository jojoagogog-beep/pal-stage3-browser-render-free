import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { data, isRouteErrorResponse, useLoaderData, useRouteError, useSearchParams, useRevalidator } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { MultiDashboard } from "../components/multi-dashboard";
import { getShopify, getSlug } from "../multi-shopify.server";
import { ruleModules } from "../rules";

const PRODUCTS_QUERY=`#graphql
query PalGuardProducts($cursor:String){
  products(first:100,after:$cursor,sortKey:ID){
    nodes{id title vendor productType tags handle descriptionHtml
      variants(first:100){nodes{id title sku barcode price compareAtPrice selectedOptions{name value}}}
    }
    pageInfo{hasNextPage endCursor}
  }
}`;
const INVENTORY_PRODUCT_QUERY=`#graphql
query PalInventoryAvailabilityProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id legacyResourceId title status variants(first:100){pageInfo{hasNextPage} nodes{id legacyResourceId title inventoryPolicy inventoryQuantity inventoryItem{tracked inventoryLevels(first:100){pageInfo{hasNextPage} nodes{quantities(names:["available"]){name quantity}}}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const SHIPPING_PRODUCT_QUERY=`#graphql
query PalShippingWeightProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id title variants(first:100){nodes{id title inventoryItem{requiresShipping measurement{weight{value unit}}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const AGE_PRODUCT_QUERY=`#graphql
query PalActiveAgeProducts($cursor:String){
  products(first:100,after:$cursor,sortKey:ID){
    nodes{id title status updatedAt}
    pageInfo{hasNextPage endCursor}
  }
}`;
const IMAGE_ALT_QUERY=`#graphql
query PalImageAltProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id title images(first:10){nodes{altText}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const COLLECTIONS_QUERY=`#graphql
query PalGuardCollections($cursor:String){
  collections(first:100,after:$cursor,sortKey:ID){
    nodes{id title handle sortOrder image{width height}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_TEMPLATE_QUERY=`#graphql
query PausedTemplateAudit($cursor:String){
 products(first:100,after:$cursor,sortKey:ID){nodes{id title templateSuffix vendor productType} pageInfo{hasNextPage endCursor}}
}`;
const PAUSED_CATEGORY_QUERY=`#graphql
query PausedCategoryAudit($cursor:String){
 products(first:50,after:$cursor,sortKey:ID){nodes{id title category{id fullName} metafields(first:250){nodes{namespace key value type}}} pageInfo{hasNextPage endCursor}}
}`;
const PAUSED_MEDIA_QUERY=`#graphql
query PausedMediaAudit($cursor:String){
 products(first:100,after:$cursor,sortKey:ID){nodes{id title media(first:20){nodes{mediaContentType}}} pageInfo{hasNextPage endCursor}}
}`;
const PAUSED_DESCRIPTION_QUERY=`#graphql
query PausedDescriptionAudit($cursor:String){
 products(first:100,after:$cursor,sortKey:ID){nodes{id title descriptionHtml} pageInfo{hasNextPage endCursor}}
}`;
const PAUSED_COLLECTION_CONTENT_QUERY=`#graphql
query PausedCollectionAudit($cursor:String){
 collections(first:100,after:$cursor,sortKey:ID){nodes{id title description image{url altText} seo{title description}} pageInfo{hasNextPage endCursor}}
}`;
const PAUSED_CATEGORY_DEFINITIONS_QUERY=`#graphql
query PausedCategoryDefinitions($cursor:String){
 metafieldDefinitions(first:100,after:$cursor,ownerType:PRODUCT,constraintStatus:CONSTRAINED_ONLY){
  nodes{id name namespace key constraints{key values(first:250){nodes{value}}}}
  pageInfo{hasNextPage endCursor}
 }
}`;
async function loadPausedCategoryDefinitions(admin:any){
 const out:any[]=[];let cursor:string|null=null;
 for(let i=0;i<10;i++){
  const response:Response=await admin.graphql(PAUSED_CATEGORY_DEFINITIONS_QUERY,{variables:{cursor}});
  const json:any=await response.json();const c=json.data?.metafieldDefinitions;
  if(!response.ok||json.errors?.length||!c)throw new Error("Could not read category field definitions.");
  for(const d of c.nodes||[]){
   if(d.constraints?.key!=="category")continue;
   const categories=(d.constraints.values?.nodes||[]).map((x:any)=>String(x.value||"").trim()).filter(Boolean);
   if(categories.length)out.push({id:d.id,name:d.name,namespace:d.namespace,key:d.key,categoryValues:categories});
  }
  if(!c.pageInfo.hasNextPage||!c.pageInfo.endCursor)break;cursor=c.pageInfo.endCursor;
 }
 return out;
}

export async function loader({request}:LoaderFunctionArgs){
  const slug=getSlug(request);const definition=ruleModules[slug as keyof typeof ruleModules] as any;
  const {admin,session}=await getShopify(slug).authenticate.admin(request);
  const paidHandles: Record<string,string>={
    "pal-collection-image-ratio-guard":"pal-collection-ratio-guard",
    "pal-collection-sort-guard":"pal-collection-sort-guard",
    "pal-product-image-alt-guard":"pal-product-image-alt-guard",
    "pal-active-product-age-guard":"pal-active-product-age-guard",
  };
  const storeHandle=String(session.shop||"").replace(/\.myshopify\.com$/i,"");
  const pricingUrl=paidHandles[slug] && /^[a-z0-9-]+$/.test(storeHandle)
    ? `https://admin.shopify.com/store/${encodeURIComponent(storeHandle)}/charges/${paidHandles[slug]}/pricing_plans`
    : null;
  const cursor=new URL(request.url).searchParams.get("cursor");
  if(cursor&&(cursor.length>2048||!/^[A-Za-z0-9+/=_-]+$/.test(cursor)))throw new Response("Invalid catalog cursor.",{status:400});
  const isCollection=definition.appMeta.entityKind==="collection";
  try{
    const query=
      slug==="pal-product-template-guard"?PAUSED_TEMPLATE_QUERY:
      slug==="pal-category-attribute-coverage-guard"?PAUSED_CATEGORY_QUERY:
      slug==="pal-product-media-count-guard"?PAUSED_MEDIA_QUERY:
      slug==="pal-product-description-guard"?PAUSED_DESCRIPTION_QUERY:
      slug==="pal-stale-draft-product-guard"?AGE_PRODUCT_QUERY:
      slug==="pal-collection-content-guard"?PAUSED_COLLECTION_CONTENT_QUERY:
      slug==="pal-product-image-alt-guard"?IMAGE_ALT_QUERY:
      slug==="pal-active-product-age-guard"?AGE_PRODUCT_QUERY:
      slug==="pal-inventory-availability-guard"?INVENTORY_PRODUCT_QUERY:
      slug==="pal-shipping-weight-integrity-guard"?SHIPPING_PRODUCT_QUERY:
      isCollection?COLLECTIONS_QUERY:PRODUCTS_QUERY;
    const response=await admin.graphql(query,{variables:{cursor}});
    const json=await response.json() as any;
    const connection=isCollection?json.data?.collections:json.data?.products;
    if(!response.ok||json.errors?.length||!connection)throw new Error("API error");
    if(connection.pageInfo.hasNextPage&&(!connection.pageInfo.endCursor||connection.pageInfo.endCursor===cursor))throw new Error("Invalid pagination");
    const definitions=slug==="pal-category-attribute-coverage-guard"?await loadPausedCategoryDefinitions(admin):undefined;
    return data({slug,pricingUrl,audit:definition.auditCatalog(connection.nodes,definitions),nextCursor:connection.pageInfo.hasNextPage?connection.pageInfo.endCursor:null,scannedAt:new Date().toISOString(),laterBatch:Boolean(cursor)},{headers:{"Cache-Control":"no-store"}});
  }catch{throw new Response("The catalog audit could not be loaded. Retry shortly.",{status:502});}
}
export default function Index(){
  const result=useLoaderData<typeof loader>();const definition=ruleModules[result.slug as keyof typeof ruleModules] as any;
  const[params,setParams]=useSearchParams();const revalidator=useRevalidator();
  return <MultiDashboard definition={definition} {...result} busy={revalidator.state==="loading"} onRefresh={()=>revalidator.revalidate()}
    onNext={result.nextCursor?()=>{const n=new URLSearchParams(params);n.set("cursor",result.nextCursor!);setParams(n)}:undefined}
    onRestart={()=>{const n=new URLSearchParams(params);n.delete("cursor");setParams(n)}}/>;
}
export function ErrorBoundary(){const error=useRouteError();const retry=useRevalidator();if(isRouteErrorResponse(error)&&[400,502].includes(error.status))return <main style={{padding:32,fontFamily:"system-ui"}}><h1>Audit unavailable</h1><p role="alert">{String(error.data)}</p><button onClick={()=>retry.revalidate()}>Try again</button></main>;return boundary.error(error)}
export const headers:HeadersFunction=(args)=>({...boundary.headers(args),"Cache-Control":"no-store"});
