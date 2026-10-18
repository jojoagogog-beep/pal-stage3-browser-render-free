import { useState } from 'react';
import { useAppBridge } from '@shopify/app-bridge-react';

export function DiscountBillingWidget() {
  const bridge = useAppBridge();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [confirmation,setConfirmation]=useState('');

  async function startSubscription(){
    if(busy)return;
    setBusy(true);setError('');setConfirmation('');
    try{
      const token=await bridge.idToken();
      if(!token || token.length<40)throw new Error('Shopify session expired. Reopen the app.');
      const response=await fetch('/app/billing-api',{
        method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({'_intent':'start_standard_trial'}).toString(),
        cache:'no-store',credentials:'same-origin'
      });
      if(!response.ok)throw new Error('Shopify could not start billing ('+response.status+').');
      const data=await response.json() as {confirmationUrl?:string};
      const u=new URL(data.confirmationUrl || '');
      if(u.protocol!=='https:' ||
        !(u.hostname==='admin.shopify.com'||u.hostname.endsWith('.myshopify.com')))
        throw new Error('Unexpected billing destination.');
      setConfirmation(u.toString());
      window.open(u.toString(),'_top');
    }catch(e){setError(e instanceof Error?e.message:'Shopify billing is unavailable.')}
    finally{setBusy(false);}
  }

  return <section aria-label="Subscription plan" style={{
      padding:20,borderRadius:10,border:'1px solid #b2d2e5',background:'#f2f8ff',
      margin:'0 0 20px',fontFamily:'system-ui',color:'#132b45'
    }}>
    <h2 style={{fontSize:19,margin:'0 0 8px'}}>Subscription plan</h2>
    <p style={{margin:'0 0 14px'}}><strong>Standard · US$5.99 every 30 days after a 7-day trial.</strong><br/>
    Secure subscription approval is managed entirely by Shopify. Development-store tests do not result in actual charges.</p>
    <button type="button" disabled={busy} onClick={()=>void startSubscription()}
      style={{background:'#173b5a',color:'#fff',border:'none',padding:'12px 16px',
        borderRadius:8,cursor:busy?'wait':'pointer',fontWeight:700}}>
      {busy?'Connecting to Shopify…':'Start 7-day trial through Shopify →'}
    </button>
    {error && <p role="alert" style={{color:'#a12c2c'}}>{error}</p>}
    {confirmation && <p><a href={confirmation} target="_top" rel="noopener noreferrer">Continue to Shopify billing approval →</a></p>}
  </section>;
}
