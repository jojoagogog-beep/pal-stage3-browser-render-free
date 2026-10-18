import type {ActionFunctionArgs} from "react-router";
import {getShopify,getSlug} from "../multi-shopify.server";

// Authenticated Shopify Billing API resource endpoint (no UI document POST).
// App Bridge supplies a fresh signed Shopify session token on each request.
export async function action({request}:ActionFunctionArgs){
  const slug=getSlug(request);
  if(slug!=="pal-collection-sort-guard"&&slug!=="pal-collection-image-ratio-guard")
    throw new Response("Unknown billing app",{status:404});
  if(request.method!=="POST")throw new Response("Method not allowed",{status:405});
  const {admin,session}=await getShopify(slug).authenticate.admin(request);
  const form=await request.formData();
  if(form.get("_intent")!=="start_standard_trial")
    throw new Response("Unsupported billing action",{status:400});
  const shop=String(session.shop||"");
  if(!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(shop))
    throw new Response("Invalid store session",{status:400});

  // The known PAL developer store always receives a test charge; never
  // allow plan inspection results to turn this into a real charge.
  let isTest=shop==="pal-safari-monitor-test-store.myshopify.com";
  if(!isTest){
    try{
      const planRes=await admin.graphql("#graphql query PalBillingDevStore { shop { plan { partnerDevelopment } } }");
      const planJson=await planRes.json() as any;
      if(planRes.ok&&!planJson.errors?.length&&planJson.data?.shop?.plan?.partnerDevelopment===true)
        isTest=true;
    }catch{/* Production stores must not silently receive test subscriptions. */}
  }

  const returnUrl=new URL("/"+slug+"/app","https://pal-stage3-browser-free-shard1.onrender.com");
  returnUrl.searchParams.set("shop",shop);
  const response=await admin.graphql(`#graphql
    mutation PalCreateSubscription($name:String!,$returnUrl:URL!,$test:Boolean,$trialDays:Int,$lineItems:[AppSubscriptionLineItemInput!]!){
      appSubscriptionCreate(name:$name,returnUrl:$returnUrl,test:$test,trialDays:$trialDays,lineItems:$lineItems){
        confirmationUrl userErrors{field message}
      }
    }`,{variables:{
    name:"Standard",returnUrl:returnUrl.toString(),test:isTest,trialDays:7,
    lineItems:[{plan:{appRecurringPricingDetails:{price:{amount:4.99,currencyCode:"USD"},interval:"EVERY_30_DAYS"}}}],
  }});
  const payload=await response.json() as any;
  const result=payload.data?.appSubscriptionCreate;
  if(!response.ok||payload.errors?.length||result?.userErrors?.length||typeof result?.confirmationUrl!=="string"){
    console.error("PAL_RESOURCE_BILLING_FAILED",slug,{status:response.status,
      messages:result?.userErrors?.map((e:any)=>String(e.message).slice(0,120)).slice(0,4)||[],
      graphqlErrors:payload.errors?.map((e:any)=>String(e.message).slice(0,120)).slice(0,4)||[]});
    throw new Response("Shopify could not create a subscription approval link",{status:502});
  }
  const target=new URL(result.confirmationUrl);
  if(target.protocol!=="https:"||
    !(target.hostname==="admin.shopify.com"||target.hostname.endsWith(".myshopify.com")))
    throw new Response("Unexpected Shopify billing destination",{status:502});
  return Response.json({confirmationUrl:target.toString()},{
    headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}
  });
}
