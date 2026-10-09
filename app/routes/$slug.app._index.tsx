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
export async function loader({request}:LoaderFunctionArgs){
  const slug=getSlug(request);const definition=ruleModules[slug as keyof typeof ruleModules] as any;
  const {admin,session}=await getShopify(slug).authenticate.admin(request);
  const paidHandles: Record<string,string>={
    "pal-collection-image-ratio-guard":"pal-collection-ratio-guard",
    "pal-collection-sort-guard":"pal-collection-sort-guard",
    "pal-product-image-alt-guard":"pal-product-image-alt-guard",
  };
  const storeHandle=String(session.shop||"").replace(/\.myshopify\.com$/i,"");
  const pricingUrl=paidHandles[slug] && /^[a-z0-9-]+$/.test(storeHandle)
    ? `https://admin.shopify.com/store/${encodeURIComponent(storeHandle)}/charges/${paidHandles[slug]}/pricing_plans`
    : null;
  const cursor=new URL(request.url).searchParams.get("cursor");
  if(cursor&&(cursor.length>2048||!/^[A-Za-z0-9+/=_-]+$/.test(cursor)))throw new Response("Invalid catalog cursor.",{status:400});
  const isCollection=definition.appMeta.entityKind==="collection";
  try{
    const response=await admin.graphql(isCollection?COLLECTIONS_QUERY:slug==="pal-product-image-alt-guard"?IMAGE_ALT_QUERY:PRODUCTS_QUERY,{variables:{cursor}});
    const json=await response.json() as any;
    const connection=isCollection?json.data?.collections:json.data?.products;
    if(!response.ok||json.errors?.length||!connection)throw new Error("API error");
    if(connection.pageInfo.hasNextPage&&(!connection.pageInfo.endCursor||connection.pageInfo.endCursor===cursor))throw new Error("Invalid pagination");
    return data({slug,pricingUrl,audit:definition.auditCatalog(connection.nodes),nextCursor:connection.pageInfo.hasNextPage?connection.pageInfo.endCursor:null,scannedAt:new Date().toISOString(),laterBatch:Boolean(cursor)},{headers:{"Cache-Control":"no-store"}});
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
