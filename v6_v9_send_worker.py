from __future__ import annotations
import asyncio, json, time
from urllib.parse import urlsplit
import v9_send_worker as ctl
from browser_slots_v7 import BrowserSlots


def base(t):
    return {'kind':'PAL_V9_SEND_RESULT_V1','token_id':str(t.get('token_id') or ''),'company_key':str(t.get('company_key') or ''),'route_id':int(t.get('route_id') or 0),'at_epoch':int(time.time())}

def v6_context(t):
    url=str(t.get('canonical_url') or '')
    domain=str(t.get('official_domain') or (urlsplit(url).hostname or '')).lower().removeprefix('www.')
    market=str(t.get('market') or '')
    detail={
        'proof_source':str(t.get('proof_stage3_source') or 'RENDERED_BROWSER_V2'),
        'lane_mode':str(t.get('proof_lane_mode') or 'FAST_DOM').upper(),
        'frame_index':t.get('proof_frame_index'),'form_index':t.get('proof_form_index'),
        'submit_text':t.get('proof_submit_text'),'form_fingerprint':t.get('proof_form_fingerprint'),
        'control_kind':('CONFIRM_STEP' if t.get('proof_confirm_step') else 'DIRECT_SUBMIT'),
    }
    route_meta={'canonical_url':url,'company_source_url':url,'domain':domain,'market':market,
                'name':str(t.get('company_key') or domain),'legal_verified':True,
                'source_kind':'V9_VERIFIED','reject_code':'','safety_flags_json':'[]'}
    reservoir={'canonical_url':url,'official_domain':domain,'market':market,
               '_v9_preverified':True,
               '_stage3_full_v3_fresh':True,
               '_stage3_full_v3_detail_json':json.dumps(detail,ensure_ascii=False),
               '_stage3_full_v3_field_schema_json':json.dumps(t.get('proof_field_schema') or [],ensure_ascii=False),
               '_stage3_static_full_fresh':False,'_stage3_static_full_detail_json':'{}'}
    return route_meta,reservoir

async def process_v6(bs,slot,t):
    out=base(t); clicked=False
    try:
        if not out['token_id'] or not t.get('canonical_url') or not t.get('message_body'):
            return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'INVALID_TASK','evidence':{'pre_submit':True}}
        if t.get('click_started') is True:
            return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'CLICK_ALREADY_STARTED_FAIL_CLOSED','evidence':{'click_started':True,'resend_safe':False}}
        if t.get('submit_started') is not True:
            return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':'SUBMIT_BARRIER_MISSING','evidence':{'pre_submit':True}}
        if not ctl._proof_control_ok(t,30000):
            return {**out,'outcome':'TECH_RETRY','reason':'PROOF_EXPIRED_PRE_BROWSER','evidence':{'pre_submit':True}}
        if not await asyncio.to_thread(ctl._production_control_ok):
            return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_BROWSER','evidence':{'pre_submit':True}}
        meta,row=v6_context(t)
        prep=await asyncio.wait_for(bs.prepare_same_page(slot,meta,row,str(t['message_body']),str(t.get('reply_address') or '')),timeout=22.0)
        if prep.get('safe') is not True or prep.get('prepared') is not True:
            outcome='SAFETY_BLOCKED' if prep.get('safety') is True else 'TECH_RETRY'
            return {**out,'outcome':outcome,'reason':str(prep.get('reason') or 'V6_PREPARE_FAILED'),'evidence':{'pre_submit':True,'v6_prepare':prep}}
        form_index=prep.get('target_form_index')
        control=await bs.final_submit_control(slot,form_index)
        confirm=None
        if control.get('ready') is not True:
            confirm=await bs.confirmation_control(slot,form_index)
            if confirm.get('ready') is not True:
                return {**out,'outcome':'CONFIRMED_NOT_SENT','reason':str(control.get('reason') or confirm.get('reason') or 'SUBMIT_CONTROL_NOT_FOUND'),'evidence':{'pre_submit':True,'v6_prepare':prep}}
        persist=await bs.revalidate_prepared_fields(slot,form_index,str(t['message_body']),str(t.get('reply_address') or ''),str(t.get('market') or ''))
        if persist.get('ready') is not True:
            outcome='SAFETY_BLOCKED' if persist.get('safety') is True else 'TECH_RETRY'
            return {**out,'outcome':outcome,'reason':str(persist.get('reason') or 'V6_PERSISTENCE_FAILED'),'evidence':{'pre_submit':True,'v6_persistence':persist}}
        async with bs.critical_submit:
            if not await asyncio.to_thread(ctl._production_control_ok):
                return {**out,'outcome':'TECH_RETRY','reason':'PRODUCTION_CONTROL_REVOKED_PRE_CLICK','evidence':{'pre_submit':True}}
            if not await asyncio.to_thread(ctl._mark_click_started,t):
                return {**out,'outcome':'TECH_RETRY','reason':'CLICK_BARRIER_WRITE_FAILED','evidence':{'pre_submit':True}}
            clicked=True
            if confirm is not None:
                cr=await asyncio.wait_for(bs.advance_confirmation(slot,int(confirm['index']),form_index),timeout=18.0)
                if cr.get('outcome')=='SENT_CONFIRMED':
                    return {**out,'outcome':'SENT_CONFIRMED','reason':str(cr.get('reason') or 'V6_CONFIRM_SENT'),'evidence':cr.get('evidence') or {}}
                if cr.get('advanced') is not True:
                    oc=str(cr.get('outcome') or 'AMBIGUOUS_HOLD')
                    if oc not in {'CONFIRMED_NOT_SENT','AMBIGUOUS_HOLD'}: oc='AMBIGUOUS_HOLD'
                    return {**out,'outcome':oc,'reason':str(cr.get('reason') or 'V6_CONFIRM_AMBIGUOUS'),'evidence':cr.get('evidence') or {}}
                final=cr.get('final_control') or {}
                if final.get('ready') is not True:
                    return {**out,'outcome':'AMBIGUOUS_HOLD','reason':'V6_CONFIRM_NO_FINAL','evidence':cr.get('evidence') or {}}
                sub=await asyncio.wait_for(bs.submit_prepared(slot,int(final['index']),final.get('form_index',form_index)),timeout=18.0)
            else:
                sub=await asyncio.wait_for(bs.submit_prepared(slot,int(control['index']),form_index),timeout=18.0)
        oc=str(sub.get('outcome') or 'AMBIGUOUS_HOLD')
        if oc not in {'SENT_CONFIRMED','CONFIRMED_NOT_SENT','AMBIGUOUS_HOLD','SAFETY_BLOCKED'}: oc='AMBIGUOUS_HOLD'
        return {**out,'outcome':oc,'reason':str(sub.get('reason') or ('V6_'+oc)),'evidence':sub.get('evidence') or {}}
    except asyncio.TimeoutError:
        return {**out,'outcome':('AMBIGUOUS_HOLD' if clicked else 'TECH_RETRY'),'reason':('V6_POST_CLICK_TIMEOUT' if clicked else 'V6_PRE_CLICK_TIMEOUT'),'evidence':{'click_started':clicked,'pre_submit':not clicked}}
    except Exception as e:
        return {**out,'outcome':('AMBIGUOUS_HOLD' if clicked else 'TECH_RETRY'),'reason':'V6_WORKER_'+type(e).__name__.upper(),'evidence':{'click_started':clicked,'detail':str(e)[:220]}}

async def main():
    q=ctl._get(ctl.TASK_URL)
    tasks=[x for x in (q.get('tasks') or []) if isinstance(x,dict) and x.get('kind')=='PAL_V9_SEND_TASK_V1' and (0 if str(x.get('sender_shard',1)).strip()=='0' else 1)==ctl.SENDER_SHARD][:8]
    armed=await asyncio.gather(*(ctl.await_submit_barrier(t,5.0) for t in tasks))
    ready=[x for x in armed if x is not None]
    if not ready:
        print(json.dumps({'status':'PASS','engine':'V6_BROWSER_SLOTS','tasks':0,'results':[]})); return
    bs=BrowserSlots(1); await bs.start(); results=[]; lock=asyncio.Lock(); queue=asyncio.Queue()
    for t in ready: queue.put_nowait(t)
    async def lane(slot):
        while not queue.empty():
            try:t=queue.get_nowait()
            except asyncio.QueueEmpty:return
            res=await process_v6(bs,slot,t)
            await asyncio.to_thread(ctl.publish_one_result_sync,res)
            async with lock: results.append(res)
            try: await bs.recycle_slot(slot)
            except Exception: pass
            queue.task_done()
    try:
        await asyncio.gather(*(lane(s) for s in list(bs.slots)))
    finally:
        await bs.close()
    print(json.dumps({'status':'PASS','engine':'V6_BROWSER_SLOTS','tasks':len(ready),'concurrency':1,'results':[{k:r.get(k) for k in ('token_id','outcome','reason')} for r in results]},ensure_ascii=False))

if __name__=='__main__': asyncio.run(main())
