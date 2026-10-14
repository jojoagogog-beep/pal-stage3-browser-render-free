// Local HTTP smoke test; NEVER needs or loads live Shopify secrets.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import net from "node:net";
import {setTimeout as sleep} from "node:timers/promises";

const slugs=[
  "pal-variant-image-guard",
  "pal-variant-order-guard",
  "pal-feed-readiness-guard",
  "pal-import-row-integrity-guard",
];
const envNames=[
  ["PAL_VARIANT_IMAGE_KEY","PAL_VARIANT_IMAGE_SECRET"],
  ["PAL_VARIANT_ORDER_KEY","PAL_VARIANT_ORDER_SECRET"],
  ["PAL_FEED_READINESS_KEY","PAL_FEED_READINESS_SECRET"],
  ["PAL_IMPORT_ROW_INTEGRITY_KEY","PAL_IMPORT_ROW_INTEGRITY_SECRET"],
];
async function freePort(){
  const socket=net.createServer();
  await new Promise(resolve=>socket.listen(0,"127.0.0.1",resolve));
  const {port}=socket.address();
  await new Promise(resolve=>socket.close(resolve));
  return port;
}
async function run(credentialMode){
  const port=await freePort();
  const env={...process.env,PORT:String(port),
    BATCH50_PUBLIC_ORIGIN:"https://pal-stage3-browser-free-shard1.onrender.com"};
  for(const [key,secret] of envNames){
    delete env[key];delete env[secret];
    if(credentialMode==="dummy"){
      env[key]="0123456789abcdef0123456789abcdef";
      env[secret]="localtestsecret012345678901234567";
    }
  }
  const child=spawn(process.execPath,[
    "node_modules/@react-router/serve/bin.js","./build/server/index.js",
  ],{cwd:process.cwd(),env,stdio:"ignore"});
  try{
    const origin="http://127.0.0.1:"+port;
    let ready=false;
    for(let i=0;i<80;i++){
      if(child.exitCode!==null)throw new Error("Server exited before ready");
      try{
        const res=await fetch(origin+"/"+slugs[0]+"/privacy");
        if(res.status===200){ready=true;break;}
      }catch{}
      await sleep(100);
    }
    assert.ok(ready,"Server did not become ready");
    let checked=0;
    for(const slug of slugs){
      for(const page of ["","privacy","terms","support","review-demo"]){
        const res=await fetch(origin+"/"+slug+"/"+page);
        assert.equal(res.status,200,slug+"/"+page);
        const html=await res.text();
        assert.match(html,/Practical AI Lab|PAL /,slug+"/"+page);
        if(page==="review-demo"){
          const uniqueDemoHint={
            "pal-variant-image-guard": "Trail Daypack",
            "pal-variant-order-guard": "Variant",
            "pal-feed-readiness-guard": "Trail Daypack",
            "pal-import-row-integrity-guard": "CSV",
          }[slug];
          assert.ok(html.includes(uniqueDemoHint),"Demo audit UI not rendered for "+slug);
        }
        checked++;
      }
      const protectedRes=await fetch(origin+"/"+slug+"/app");
      assert.ok(protectedRes.status>=400,
        "Unauthenticated /app must not return success for "+slug);
      if(credentialMode==="dummy"){
        assert.equal(protectedRes.status,410,
          "No-session embedded app must be rejected before viewing catalog for "+slug);
      }
      checked++;
      if(credentialMode==="dummy"){
        for(const topic of ["customers/data_request","customers/redact","app/uninstalled"]){
          const webhook=await fetch(origin+"/"+slug+"/webhooks/"+topic,{
            method:"POST",headers:{"content-type":"application/json"},body:"{}"
          });
          assert.equal(webhook.status,400,
            "Unsigned Shopify compliance webhook must fail HMAC before execution: "+slug+"/"+topic);
          checked++;
        }
      }
    }
    console.log("PASS",credentialMode,checked,"HTTP checks");
  }finally{
    child.kill("SIGTERM");
    await sleep(250);
    if(child.exitCode===null)child.kill("SIGKILL");
  }
}
await run("missing");
await run("dummy");
console.log("ALL PAUSED SHOPIFY APP HTTP SMOKE CHECKS PASSED");
