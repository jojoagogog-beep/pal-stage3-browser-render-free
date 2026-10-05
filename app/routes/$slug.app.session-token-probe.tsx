import type { LoaderFunctionArgs } from "react-router";
import { getShopify, getSlug } from "../multi-shopify.server";
export async function loader({request}:LoaderFunctionArgs){const slug=getSlug(request);await getShopify(slug).authenticate.admin(request);return new Response(null,{status:204,headers:{"Cache-Control":"no-store","Pragma":"no-cache"}})}
export default function SessionTokenProbe(){return null}
