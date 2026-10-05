import type { HeadersFunction, LoaderFunctionArgs } from 'react-router';
import { data, isRouteErrorResponse, useLoaderData, useRouteError, useSearchParams, useRevalidator } from 'react-router';
import { boundary } from '@shopify/shopify-app-react-router/server';
import { DescriptionDashboard } from '../components/description-dashboard';
import { auditCatalog, type Product } from '../lib/description-audit';
import { authenticate } from '../shopify.server';

export const PRODUCTS_QUERY = [
  '#graphql',
  'query PalGuardProducts($cursor:String){',
  '  products(first:100,after:$cursor,sortKey:ID){',
  '    nodes{',
  '      id title vendor tags handle descriptionHtml',
  '      variants(first:100){nodes{id title sku barcode price compareAtPrice selectedOptions{name value}}}',
  '    }',
  '    pageInfo{hasNextPage endCursor}',
  '  }',
  '}'
].join('\n');

export async function loader({request}:LoaderFunctionArgs){
  const {admin}=await authenticate.admin(request);
  const cursor=new URL(request.url).searchParams.get('cursor');
  if(cursor&&(cursor.length>2048||!/^[A-Za-z0-9+/=_-]+$/.test(cursor))) throw new Response('Invalid catalog cursor.',{status:400});
  try{
    const response=await admin.graphql(PRODUCTS_QUERY,{variables:{cursor}});
    const json=await response.json() as {errors?:unknown[];data?:{products:{nodes:Product[];pageInfo:{hasNextPage:boolean;endCursor:string|null}}}};
    if(!response.ok||json.errors?.length||!json.data?.products) throw new Error('API error');
    const result=json.data.products;
    if(result.pageInfo.hasNextPage&&(!result.pageInfo.endCursor||result.pageInfo.endCursor===cursor)) throw new Error('Invalid pagination');
    return data({audit:auditCatalog(result.nodes),nextCursor:result.pageInfo.hasNextPage?result.pageInfo.endCursor:null,scannedAt:new Date().toISOString(),laterBatch:Boolean(cursor)},{headers:{'Cache-Control':'no-store'}});
  }catch{
    throw new Response('The catalog audit could not be loaded. Retry shortly. If it continues, check product access or contact support.',{status:502});
  }
}
export default function Index(){
  const result=useLoaderData<typeof loader>(); const [params,setParams]=useSearchParams(); const revalidator=useRevalidator();
  return <DescriptionDashboard {...result} busy={revalidator.state==='loading'} onRefresh={()=>revalidator.revalidate()}
    onNext={result.nextCursor?()=>{const next=new URLSearchParams(params);next.set('cursor',result.nextCursor!);setParams(next);}:undefined}
    onRestart={()=>{const next=new URLSearchParams(params);next.delete('cursor');setParams(next);}}/>;
}
export function ErrorBoundary(){
  const error=useRouteError(); const retry=useRevalidator();
  if(isRouteErrorResponse(error)&&[400,502].includes(error.status)) return <main style={{padding:32,fontFamily:'system-ui'}}><h1>Audit unavailable</h1><p role='alert'>{String(error.data)}</p><button onClick={()=>retry.revalidate()}>Try again</button> <a href='/support' target='_blank' rel='noreferrer'>Support</a></main>;
  return boundary.error(error);
}
export const headers:HeadersFunction=args=>({...boundary.headers(args),'Cache-Control':'no-store'});
