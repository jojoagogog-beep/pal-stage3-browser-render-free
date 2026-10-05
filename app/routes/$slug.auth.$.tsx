import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { getShopify, getSlug } from "../multi-shopify.server";
export async function loader({request}:LoaderFunctionArgs){const slug=getSlug(request);await getShopify(slug).authenticate.admin(request);return null}
export const headers:HeadersFunction=(args)=>boundary.headers(args);
