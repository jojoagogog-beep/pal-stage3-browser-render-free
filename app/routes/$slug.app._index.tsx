import type { HeadersFunction, LoaderFunctionArgs, ActionFunctionArgs } from "react-router";
import { data, isRouteErrorResponse, useLoaderData, useRouteError, useSearchParams, useRevalidator, useParams } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { MultiDashboard } from "../components/multi-dashboard";
import { getShopify, getSlug } from "../multi-shopify.server";
import { ruleModules } from "../rules";

import variantImageUI from "../special/variant-image/ui";
import variantOrderUI from "../special/variant-order/ui";
import feedReadinessUI from "../special/feed-readiness/ui";
import importIntegrityUI from "../special/import-row-integrity/ui";
const specialRoutes:Record<string,any>={
"pal-variant-image-guard":variantImageUI,
"pal-variant-order-guard":variantOrderUI,
"pal-feed-readiness-guard":feedReadinessUI,
"pal-import-row-integrity-guard":importIntegrityUI,
};

const PRODUCTS_QUERY=`#graphql
query PalGuardProducts($cursor:String){
  products(first:100,after:$cursor,sortKey:ID){
    nodes{id title vendor productType tags handle descriptionHtml
      variants(first:100){nodes{id title sku barcode price compareAtPrice selectedOptions{name value}}}
    }
    pageInfo{hasNextPage endCursor}
  }
}`;
// Additional paused-review apps use cost-bounded, product-specific Shopify
// GraphQL queries. They never write merchant catalog data.
const EXTRA_IMAGES_QUERY=`#graphql
query PalImageReview($cursor:String){
 products(first:35,after:$cursor,sortKey:ID){
  nodes{id title images(first:10){nodes{width height}}}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_STOCK_QUERY=`#graphql
query PalStockReview($cursor:String){
 products(first:10,after:$cursor,sortKey:ID){
  nodes{id title status variants(first:50){pageInfo{hasNextPage} nodes{id title inventoryQuantity inventoryItem{tracked}}}}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_VARIANT_QUERY=`#graphql
query PalVariantsReview($cursor:String){
 products(first:10,after:$cursor,sortKey:ID){
  nodes{id title options{name values} variants(first:75){pageInfo{hasNextPage} nodes{id title}}}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_SEO_QUERY=`#graphql
query PalSeoDuplicates($cursor:String){
 products(first:75,after:$cursor,sortKey:ID){
  nodes{id title seo{title description}}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_DESC_QUERY=`#graphql
query PalDescriptionReview($cursor:String){
 products(first:75,after:$cursor,sortKey:ID){
  nodes{id title descriptionHtml}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_TAG_HANDLE_QUERY=`#graphql
query PalTagsAndHandlesReview($cursor:String){
 products(first:100,after:$cursor,sortKey:ID){
  nodes{id title tags handle}
  pageInfo{hasNextPage endCursor}
 }
}`;
const EXTRA_COLLECTION_RULE_QUERY=`#graphql
query PalCollectionRulesReview($cursor:String){
 collections(first:30,after:$cursor,sortKey:ID){
  nodes{id title handle ruleSet{appliedDisjunctively rules{column relation condition}}}
  pageInfo{hasNextPage endCursor}
 }
}`;

const PAUSED_UNIT_COST_QUERY=`#graphql
query PalUnitCostProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id title variants(first:50){pageInfo{hasNextPage} nodes{id title sku inventoryItem{unitCost{amount currencyCode}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_CUSTOMS_QUERY=`#graphql
query PalCustomsProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id title variants(first:50){pageInfo{hasNextPage} nodes{id title inventoryItem{requiresShipping harmonizedSystemCode countryCodeOfOrigin}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_SELLING_PLAN_QUERY=`#graphql
query PalSellingPlanProducts($cursor:String){
  products(first:30,after:$cursor,sortKey:ID){
    nodes{id title variants(first:30){pageInfo{hasNextPage} nodes{id title sellingPlanGroups(first:10){pageInfo{hasNextPage} nodes{id name}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_INVENTORY_LOCATION_QUERY=`#graphql
query PalInventoryLocationProducts($cursor:String){
  products(first:10,after:$cursor,sortKey:ID){
    nodes{id title variants(first:10){pageInfo{hasNextPage} nodes{id title inventoryItem{tracked inventoryLevels(first:10){pageInfo{hasNextPage} nodes{location{id name}}}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_VARIANT_SHIPPING_QUERY=`#graphql
query PalVariantShippingProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id title variants(first:50){pageInfo{hasNextPage} nodes{id title inventoryItem{requiresShipping tracked measurement{weight{value unit}}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_DUPLICATE_SKU_QUERY=`#graphql
query PalDuplicateSkuVariants($cursor:String){
 productVariants(first:100,after:$cursor,sortKey:ID){
  nodes{id title sku product{id title}}
  pageInfo{hasNextPage endCursor}
 }
}`;
const PAUSED_SKU_FORMAT_QUERY=`#graphql
query PalSkuFormatProducts($cursor:String){
  products(first:75,after:$cursor,sortKey:ID){
    nodes{id title variants(first:100){pageInfo{hasNextPage} nodes{id title sku}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_COLLECTION_COVERAGE_QUERY=`#graphql
query PalCollectionCoverageProducts($cursor:String){
  products(first:75,after:$cursor,sortKey:ID){
    nodes{id title status collections(first:1){nodes{id}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_INVENTORY_POLICY_QUERY=`#graphql
query PalInventoryPolicyProducts($cursor:String){
  products(first:75,after:$cursor,sortKey:ID){
    nodes{id title variants(first:100){pageInfo{hasNextPage} nodes{id title inventoryPolicy}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_TAX_FLAG_QUERY=`#graphql
query PalTaxFlagProducts($cursor:String){
  products(first:75,after:$cursor,sortKey:ID){
    nodes{id title variants(first:100){pageInfo{hasNextPage} nodes{id title taxable}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const PAUSED_EMPTY_COLLECTION_QUERY=`#graphql
query PalEmptyCollections($cursor:String){
  collections(first:75,after:$cursor,sortKey:ID){
    nodes{id title handle products(first:1){nodes{id}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const OPTION_NAME_QUERY=`#graphql
query PalOptionNameProducts($cursor:String){
  products(first:100,after:$cursor,sortKey:ID){
    nodes{id title options{name position}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const SEO_FALLBACK_QUERY=`#graphql
query PalSeoFallbackProducts($cursor:String){
  products(first:50,after:$cursor,sortKey:ID){
    nodes{id legacyResourceId title description seo{title description}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const INVENTORY_PRODUCT_QUERY=`#graphql
query PalInventoryAvailabilityProducts($cursor:String){
  products(first:5,after:$cursor,sortKey:ID){
    nodes{id legacyResourceId title status variants(first:10){pageInfo{hasNextPage} nodes{id legacyResourceId title inventoryPolicy inventoryQuantity inventoryItem{tracked inventoryLevels(first:5){pageInfo{hasNextPage} nodes{quantities(names:["available"]){name quantity}}}}}}}
    pageInfo{hasNextPage endCursor}
  }
}`;
const SHIPPING_PRODUCT_QUERY=`#graphql
query PalShippingWeightProducts($cursor:String){
  products(first:10,after:$cursor,sortKey:ID){
    nodes{id title variants(first:20){pageInfo{hasNextPage} nodes{id title inventoryItem{requiresShipping measurement{weight{value unit}}}}}}
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
  const slug=getSlug(request);
  if(slug==="pal-variant-image-guard")return (await import("../special/variant-image/route.server")).loader({request} as LoaderFunctionArgs);
  if(slug==="pal-variant-order-guard")return (await import("../special/variant-order/route.server")).loader({request} as LoaderFunctionArgs);
  if(slug==="pal-feed-readiness-guard")return (await import("../special/feed-readiness/route.server")).loader({request} as LoaderFunctionArgs);
  if(slug==="pal-import-row-integrity-guard")return (await import("../special/import-row-integrity/route.server")).loader({request} as LoaderFunctionArgs);const definition=ruleModules[slug as keyof typeof ruleModules] as any;
  const {admin,session}=await getShopify(slug).authenticate.admin(request);
  if(slug==="pal-duplicate-sku-guard"){
    try{
      const variants:Array<{id:string;title:string;sku:string|null;product:{id:string;title:string}}>=[];
      let variantCursor:string|null=null;
      let truncated=false;
      for(let page=0;page<10;page++){
        const response=await admin.graphql(PAUSED_DUPLICATE_SKU_QUERY,{variables:{cursor:variantCursor}});
        const json=await response.json() as any;
        const list=json.data?.productVariants;
        if(!response.ok||json.errors?.length||!list)throw new Error("Shopify variant query failed");
        variants.push(...(list.nodes||[]));
        if(!list.pageInfo?.hasNextPage){truncated=false;break}
        if(!list.pageInfo.endCursor||list.pageInfo.endCursor===variantCursor)throw new Error("Invalid variant pagination");
        variantCursor=list.pageInfo.endCursor;
        truncated=true;
      }
      const products=new Map<string,{id:string;title:string;variants:{pageInfo:{hasNextPage:boolean};nodes:Array<{id:string;title:string;sku:string|null}>}}>();
      for(const v of variants){
        if(!v.product?.id)continue;
        const id=String(v.product.id);
        if(!products.has(id))products.set(id,{id,title:String(v.product.title||""),variants:{pageInfo:{hasNextPage:false},nodes:[]}});
        products.get(id)!.variants.nodes.push({id:String(v.id),title:String(v.title||""),sku:v.sku??null});
      }
      const audit=definition.auditCatalog([...products.values()]);
      if(truncated)audit.skipped.push("Catalog scan capped at 1,000 variants; remaining variants were not examined.");
      return data({slug,pricingUrl:null,billingAction:false,audit,nextCursor:null,scannedAt:new Date().toISOString(),laterBatch:false},{headers:{"Cache-Control":"no-store"}});
    }catch(error){
      console.error("PAL_DUPLICATE_SKU_LOAD_FAILED",error instanceof Error?error.name:"unknown");
      throw new Response("The duplicate SKU audit could not be completed. Retry shortly.",{status:502});
    }
  }
  const paidHandles: Record<string,string>={
    "pal-collection-image-ratio-guard":"430707900417",
    "pal-collection-sort-guard":"430672871425",
    "pal-product-image-alt-guard":"pal-product-image-alt-guard",
    "pal-active-product-age-guard":"pal-active-product-age-guard",
  };
  const billingAction=slug==="pal-collection-image-ratio-guard"||slug==="pal-collection-sort-guard";
  const storeHandle=String(session.shop||"").replace(/\.myshopify\.com$/i,"");
  const pricingUrl=!billingAction && paidHandles[slug] && /^[a-z0-9-]+$/.test(storeHandle)
    ? `https://admin.shopify.com/store/${encodeURIComponent(storeHandle)}/charges/${paidHandles[slug]}/pricing_plans`
    : null;
  const cursor=new URL(request.url).searchParams.get("cursor");
  if(cursor&&(cursor.length>2048||!/^[A-Za-z0-9+/=_-]+$/.test(cursor)))throw new Response("Invalid catalog cursor.",{status:400});
  const isCollection=definition.appMeta.entityKind==="collection";
  try{
    const query=
      ["pal-product-image-size-guard","pal-product-image-aspect-guard"].includes(slug)?EXTRA_IMAGES_QUERY:
      ["pal-archived-stock-guard","pal-negative-inventory-guard","pal-draft-stock-guard"].includes(slug)?EXTRA_STOCK_QUERY:
      ["pal-variant-count-guard","pal-option-complexity-guard"].includes(slug)?EXTRA_VARIANT_QUERY:
      ["pal-seo-duplicate-guard","pal-seo-length-guard"].includes(slug)?EXTRA_SEO_QUERY:
      ["pal-description-html-guard","pal-duplicate-description-guard"].includes(slug)?EXTRA_DESC_QUERY:
      ["pal-product-tag-count-guard","pal-product-handle-guard"].includes(slug)?EXTRA_TAG_HANDLE_QUERY:
      ["pal-collection-rule-guard","pal-rule-drift-guard"].includes(slug)?EXTRA_COLLECTION_RULE_QUERY:
      slug==="pal-product-template-guard"?PAUSED_TEMPLATE_QUERY:
      slug==="pal-category-attribute-coverage-guard"?PAUSED_CATEGORY_QUERY:
      slug==="pal-product-media-count-guard"?PAUSED_MEDIA_QUERY:
      slug==="pal-product-description-guard"?PAUSED_DESCRIPTION_QUERY:
      slug==="pal-stale-draft-product-guard"?AGE_PRODUCT_QUERY:
      slug==="pal-collection-content-guard"?PAUSED_COLLECTION_CONTENT_QUERY:
      slug==="pal-product-image-alt-guard"?IMAGE_ALT_QUERY:
      slug==="pal-active-product-age-guard"?AGE_PRODUCT_QUERY:
      slug==="pal-unit-cost-coverage-guard"?PAUSED_UNIT_COST_QUERY:
      slug==="pal-customs-data-readiness-guard"?PAUSED_CUSTOMS_QUERY:
      slug==="pal-selling-plan-coverage-guard"?PAUSED_SELLING_PLAN_QUERY:
      slug==="pal-inventory-location-consistency-guard"?PAUSED_INVENTORY_LOCATION_QUERY:
      slug==="pal-variant-shipping-policy-guard"?PAUSED_VARIANT_SHIPPING_QUERY:
      slug==="pal-sku-format-consistency-guard"?PAUSED_SKU_FORMAT_QUERY:
      slug==="pal-collection-coverage-guard"?PAUSED_COLLECTION_COVERAGE_QUERY:
      slug==="pal-inventory-policy-consistency-guard"?PAUSED_INVENTORY_POLICY_QUERY:
      slug==="pal-variant-tax-flag-guard"?PAUSED_TAX_FLAG_QUERY:
      slug==="pal-empty-collection-guard"?PAUSED_EMPTY_COLLECTION_QUERY:
      slug==="pal-option-name-consistency-guard"?OPTION_NAME_QUERY:
      slug==="pal-seo-fallback-readiness-guard"?SEO_FALLBACK_QUERY:
      slug==="pal-inventory-availability-guard"?INVENTORY_PRODUCT_QUERY:
      slug==="pal-shipping-weight-integrity-guard"?SHIPPING_PRODUCT_QUERY:
      isCollection?COLLECTIONS_QUERY:PRODUCTS_QUERY;
    const response=await admin.graphql(query,{variables:{cursor}});
    const json=await response.json() as any;
    const connection=isCollection?json.data?.collections:json.data?.products;
    if(!response.ok||json.errors?.length||!connection){
      // Log only safe diagnostic metadata. Never log a session token or the GraphQL response.
      console.error("PAL_AUDIT_GRAPHQL_REJECTED",slug,{
        httpStatus:response.status,
        errorCodes:(json.errors||[]).map((e:any)=>String(e.extensions?.code||"unknown")).slice(0,5),
        requestedCost:json.extensions?.cost?.requestedQueryCost??null,
      });
      throw new Error("API error");
    }
    if(connection.pageInfo.hasNextPage&&(!connection.pageInfo.endCursor||connection.pageInfo.endCursor===cursor))throw new Error("Invalid pagination");
    const definitions=slug==="pal-category-attribute-coverage-guard"?await loadPausedCategoryDefinitions(admin):undefined;
    return data({slug,pricingUrl,billingAction,audit:definition.auditCatalog(connection.nodes,definitions),nextCursor:connection.pageInfo.hasNextPage?connection.pageInfo.endCursor:null,scannedAt:new Date().toISOString(),laterBatch:Boolean(cursor)},{headers:{"Cache-Control":"no-store"}});
  }catch(error){
    console.error("PAL_AUDIT_LOAD_FAILED",slug,error instanceof Error?error.name:"unknown");
    throw new Response("The catalog audit could not be loaded. Retry shortly.",{status:502});
  }
}
export async function action(args:ActionFunctionArgs){
 const slug=getSlug(args.request);
 if(["pal-collection-image-ratio-guard","pal-collection-sort-guard"].includes(slug)){
   // These two applications are still on Manual Pricing (legacy); Shopify
   // App Pricing is NOT enabled. Use the Shopify Billing API, not a dead
   // hosted plan-selection link. All real merchant charges go via Shopify.
   if(args.request.method!=="POST")throw new Response("Method not allowed",{status:405});
   const submitted=await args.request.formData();
   if(submitted.get("_intent")!=="start_standard_trial")
     throw new Response("Unsupported billing action",{status:400});
   const {admin,redirect,session}=await getShopify(slug).authenticate.admin(args.request);
   const shop=String(session.shop||"");
   if(!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(shop))
     throw new Response("Invalid shop session",{status:400});
   // The review/test store gets a Shopify TEST charge. All ordinary
   // merchant subscriptions are real Shopify-admin charges.
   let testCharge=shop==="pal-safari-monitor-test-store.myshopify.com";
   try{
     const planResponse=await admin.graphql("#graphql query PalShopBillingPlan { shop { plan { partnerDevelopment } } }");
     const planJson=await planResponse.json() as any;
     if(planResponse.ok&&!planJson.errors?.length)
       testCharge=Boolean(planJson.data?.shop?.plan?.partnerDevelopment);
   }catch{
     // A production shop must never silently receive a test/free charge.
     testCharge=shop==="pal-safari-monitor-test-store.myshopify.com";
   }
   const returnUrl=new URL("/"+slug+"/app","https://pal-stage3-browser-free-shard1.onrender.com");
   returnUrl.searchParams.set("shop",shop);
   const response=await admin.graphql(`#graphql
     mutation PalCreateSubscription($name:String!,$returnUrl:URL!,$test:Boolean,$trialDays:Int,$lineItems:[AppSubscriptionLineItemInput!]!){
       appSubscriptionCreate(name:$name,returnUrl:$returnUrl,test:$test,trialDays:$trialDays,lineItems:$lineItems){
         confirmationUrl
         userErrors{field message}
       }
     }`,{variables:{
       name:"Standard",returnUrl:returnUrl.toString(),test:testCharge,trialDays:7,
       lineItems:[{plan:{appRecurringPricingDetails:{price:{amount:4.99,currencyCode:"USD"},interval:"EVERY_30_DAYS"}}}],
     }});
   const result=await response.json() as any;
   const details=result.data?.appSubscriptionCreate;
   const url=details?.confirmationUrl;
   if(!response.ok||result.errors?.length||details?.userErrors?.length||typeof url!=="string"){
     console.error("PAL_SHOPIFY_BILLING_API_REJECTED",slug,{http:response.status,
       errors:details?.userErrors?.map((x:any)=>String(x.message).slice(0,120)).slice(0,3)||[]});
     throw new Response("Shopify could not initiate the subscription. Retry or contact support.",{status:502});
   }
   const target=new URL(url);
   if(target.protocol!=="https:"||!([target.hostname==="admin.shopify.com",target.hostname.endsWith(".myshopify.com")].some(Boolean)))
     throw new Response("Unexpected billing host",{status:502});
   return data({confirmationUrl:url},{headers:{"Cache-Control":"no-store"}});
 }
 if(slug==="pal-variant-image-guard")return (await import("../special/variant-image/route.server")).action(args);
 if(slug==="pal-variant-order-guard")return (await import("../special/variant-order/route.server")).action(args);
 if(slug==="pal-feed-readiness-guard")return (await import("../special/feed-readiness/route.server")).action(args);
 if(slug==="pal-import-row-integrity-guard")return (await import("../special/import-row-integrity/route.server")).action(args);
 throw new Response("Unsupported action",{status:405});
}
export default function Index(){
  const {slug}=useParams();
  const SpecialPage=specialRoutes[slug||""];
  return SpecialPage?<SpecialPage/>:<StandardPage/>;
}
function StandardPage(){
  const result=useLoaderData<any>();const definition=ruleModules[result.slug as keyof typeof ruleModules] as any;
  const[params,setParams]=useSearchParams();const revalidator=useRevalidator();
  return <MultiDashboard definition={definition} {...result} busy={revalidator.state==="loading"} onRefresh={()=>revalidator.revalidate()}
    onNext={result.nextCursor?()=>{const n=new URLSearchParams(params);n.set("cursor",result.nextCursor!);setParams(n)}:undefined}
    onRestart={()=>{const n=new URLSearchParams(params);n.delete("cursor");setParams(n)}}/>;
}
export function ErrorBoundary(){const error=useRouteError();const retry=useRevalidator();if(isRouteErrorResponse(error)&&[400,502].includes(error.status))return <main style={{padding:32,fontFamily:"system-ui"}}><h1>Audit unavailable</h1><p role="alert">{String(error.data)}</p><button onClick={()=>retry.revalidate()}>Try again</button></main>;return boundary.error(error)}
export const headers:HeadersFunction=(args)=>({...boundary.headers(args),"Cache-Control":"no-store"});
