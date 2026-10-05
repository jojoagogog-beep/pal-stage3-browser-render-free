import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { Outlet, useLoaderData, useRouteError } from "react-router";
import { useEffect } from "react";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { useAppBridge } from "@shopify/app-bridge-react";
import { apiKeyFor, getShopify, getSlug } from "../multi-shopify.server";

export async function loader({request}:LoaderFunctionArgs){
  const slug=getSlug(request);
  await getShopify(slug).authenticate.admin(request);
  return {slug,apiKey:apiKeyFor(slug)};
}
function SessionTokenSignal({slug}:{slug:string}){
  const shopify=useAppBridge();
  useEffect(()=>{let cancelled=false;const send=async()=>{try{const token=await shopify.idToken();if(cancelled)return;await fetch("/"+slug+"/app/session-token-probe",{headers:{Authorization:"Bearer "+token,"Cache-Control":"no-store"},credentials:"omit",cache:"no-store"});}catch{}};
    void send();const t=window.setTimeout(()=>void send(),2500);return()=>{cancelled=true;window.clearTimeout(t)};},[shopify,slug]);
  return null;
}
export default function App(){const {apiKey,slug}=useLoaderData<typeof loader>();return <AppProvider embedded apiKey={apiKey}><SessionTokenSignal slug={slug}/><Outlet/></AppProvider>}
export function ErrorBoundary(){return boundary.error(useRouteError())}
export const headers:HeadersFunction=(args)=>boundary.headers(args);
