import { AppProvider } from "@shopify/shopify-app-react-router/react";
import type { LoaderFunctionArgs } from "react-router";
import { getShopify, getSlug } from "../../multi-shopify.server";
import { ruleModules } from "../../rules";
export async function loader({request}:LoaderFunctionArgs){const slug=getSlug(request);await getShopify(slug).login(request);return null}
export default function Auth(){return <AppProvider embedded={false}><s-page heading="Shopify authentication required"><s-section heading="Open the app from Shopify"><s-paragraph>For security, installation and sign-in start from the Shopify App Store or Shopify admin.</s-paragraph></s-section></s-page></AppProvider>}
