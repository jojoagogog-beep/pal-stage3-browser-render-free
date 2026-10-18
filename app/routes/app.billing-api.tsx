import type { ActionFunctionArgs } from 'react-router';
import { authenticate } from '../shopify.server';

// Shopify-owned subscription approval, never an external checkout.
export async function action({ request }: ActionFunctionArgs) {
  if (request.method !== 'POST') throw new Response('Method not allowed', { status: 405 });
  const { admin, session } = await authenticate.admin(request);
  const form = await request.formData();
  if (form.get('_intent') !== 'start_standard_trial') throw new Response('Unsupported action', { status: 400 });
  const shop = String(session.shop || '');
  if (!/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(shop)) throw new Response('Invalid Shopify store', { status: 400 });

  // Shopify partner development stores receive a TEST charge only.
  // Do not silently issue test billing for production merchants.
  let test = shop === 'pal-safari-monitor-test-store.myshopify.com';
  try {
    const planResponse = await admin.graphql('#graphql query PalDiscountShopPlan { shop { plan { partnerDevelopment } } }');
    const planJson = await planResponse.json() as any;
    if (planResponse.ok && !planJson.errors?.length &&
        planJson.data?.shop?.plan?.partnerDevelopment === true) test = true;
  } catch { /* A production shop must not fall back to test charging. */ }

  const returnUrl = new URL('/app', 'https://pal-discount-depth-guard.onrender.com');
  returnUrl.searchParams.set('shop', shop);
  const response = await admin.graphql(`#graphql
    mutation PalDiscountStandard($name:String!,$returnUrl:URL!,$test:Boolean,$trialDays:Int,$lineItems:[AppSubscriptionLineItemInput!]!) {
      appSubscriptionCreate(name:$name,returnUrl:$returnUrl,test:$test,trialDays:$trialDays,lineItems:$lineItems) {
        confirmationUrl userErrors { field message }
      }
    }`, { variables: {
    name: 'Standard', returnUrl: returnUrl.toString(), test, trialDays: 7,
    lineItems: [{ plan: { appRecurringPricingDetails: {
      price: { amount: 5.99, currencyCode: 'USD' }, interval: 'EVERY_30_DAYS'
    } } }]
  } });
  const payload = await response.json() as any;
  const result = payload.data?.appSubscriptionCreate;
  if (!response.ok || payload.errors?.length || result?.userErrors?.length ||
      typeof result?.confirmationUrl !== 'string') {
    console.error('PAL_DISCOUNT_SHOPIFY_BILLING_FAILED', {
      status:response.status,
      errors:result?.userErrors?.map((e:any)=>String(e.message).slice(0,90)).slice(0,3) || [],
      gql:payload.errors?.map((e:any)=>String(e.extensions?.code||'unknown')).slice(0,3) || []
    });
    throw new Response('Shopify billing approval is unavailable. Please retry.', { status: 502 });
  }
  const target = new URL(result.confirmationUrl);
  if (target.protocol !== 'https:' ||
      !(target.hostname === 'admin.shopify.com' || target.hostname.endsWith('.myshopify.com')))
    throw new Response('Invalid Shopify approval URL', { status: 502 });
  return Response.json({ confirmationUrl: target.toString() }, {
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }
  });
}
