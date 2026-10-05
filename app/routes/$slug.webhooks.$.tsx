import type { ActionFunctionArgs } from "react-router";
import db from "../db.server";
import { getShopify, getSlug } from "../multi-shopify.server";
export async function action({request}:ActionFunctionArgs){
  const slug=getSlug(request);const {shop,topic,payload}=await getShopify(slug).authenticate.webhook(request);
  if(topic==="APP_UNINSTALLED"){await db.session.deleteMany({where:{shop,id:{startsWith:slug+":"}}});}
  if(topic==="APP_SCOPES_UPDATE"){
    const current=(payload as any)?.current;
    if(!Array.isArray(current)||!current.every((v:unknown)=>typeof v==="string"))return new Response("Invalid scope payload",{status:400});
    await db.session.updateMany({where:{shop,id:{startsWith:slug+":"}},data:{scope:current.join(",")}});
  }
  return new Response(null,{status:200});
}
