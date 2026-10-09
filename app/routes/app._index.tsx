import type {ActionFunctionArgs,HeadersFunction,LoaderFunctionArgs} from "react-router";
import {useLoaderData} from "react-router";
import {boundary} from "@shopify/shopify-app-react-router/server";
import {ProductAuditDashboard} from "../components/product-audit-dashboard";
import {auditProducts,buildCsv,type ProductInput} from "../lib/product-audit";
import {authenticate} from "../shopify.server";
const MODE="active_freshness", APP_NAME="PAL Active Product Age Guard";
const QUERY=["#graphql","query ProductAudit($cursor:String,$first:Int!){","shop{name myshopifyDomain}","products(first:$first,after:$cursor,sortKey:ID){pageInfo{hasNextPage endCursor} nodes{id legacyResourceId title handle tags status updatedAt images(first:10){nodes{width height}} variants(first:50){nodes{price compareAtPrice}}}}","}"].join("\n");
async function load(admin:any){let cursor:string|null=null,more=true;const products:ProductInput[]=[];let shopName="Your store",shopDomain="";while(more&&products.length<1000){const r:Response=await admin.graphql(QUERY,{variables:{cursor,first:Math.min(100,1000-products.length)}});const j:any=await r.json();if(!r.ok||j.errors?.length||!j.data?.products)throw new Response("Product data could not be read.",{status:502});shopName=j.data.shop?.name||shopName;shopDomain=j.data.shop?.myshopifyDomain||shopDomain;products.push(...j.data.products.nodes);cursor=j.data.products.pageInfo.endCursor;more=j.data.products.pageInfo.hasNextPage&&Boolean(cursor);if(!j.data.products.nodes.length)break;}return{products,shopName,shopDomain,coverageLimited:more};}
export const loader=async({request}:LoaderFunctionArgs)=>{const{admin}=await authenticate.admin(request);const d=await load(admin);return{appName:APP_NAME,mode:MODE,shopName:d.shopName,shopDomain:d.shopDomain,audit:auditProducts(d.products,MODE),coverageLimited:d.coverageLimited,scannedAt:new Date().toISOString().slice(0,16).replace("T"," ")+" UTC"};};
export const action=async({request}:ActionFunctionArgs)=>{const{admin}=await authenticate.admin(request);const f=await request.formData();if(f.get("intent")!=="exportCsv")return new Response("Unknown action",{status:400});const d=await load(admin);return new Response(buildCsv(auditProducts(d.products,MODE),d.shopDomain),{headers:{"Content-Type":"text/csv; charset=utf-8","Content-Disposition":"attachment; filename=pal-product-audit.csv","Cache-Control":"no-store"}});};
export default function Index(){return <ProductAuditDashboard {...useLoaderData<typeof loader>()}/>;}
export const headers:HeadersFunction=(args)=>boundary.headers(args);
