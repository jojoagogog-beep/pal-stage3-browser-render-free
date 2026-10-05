import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";
import db from "../db.server";
export const action = async ({request}:ActionFunctionArgs) => {
 const {payload,shop}=await authenticate.webhook(request);
 if(!Array.isArray(payload.current)||!payload.current.every((v:unknown)=>typeof v==='string'))return new Response('Invalid scope payload',{status:400});
 await db.session.updateMany({where:{shop},data:{scope:payload.current.join(',')}});
 return new Response(null,{status:200});
};
