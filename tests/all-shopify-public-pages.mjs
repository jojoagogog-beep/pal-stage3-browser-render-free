// Regression check for every known Shopify gateway app, without OAuth secrets.
import fs from "node:fs";
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import net from "node:net";
import {setTimeout as sleep} from "node:timers/promises";

const slugs=[...fs.readFileSync("app/rules/app-env-names.ts","utf8")
  .matchAll(/^\s*'(pal-[a-z0-9-]+)':\s*\{/gm)].map(x=>x[1]);
assert.ok(slugs.length>=70,"Expected all known gateway app routes to remain registered");
const server=net.createServer();
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const port=server.address().port;
await new Promise(resolve=>server.close(resolve));
const env={...process.env,PORT:String(port),
  BATCH50_PUBLIC_ORIGIN:"https://pal-stage3-browser-free-shard1.onrender.com"};
for(const name of Object.keys(env)){
  if(name.startsWith("PAL_")&&(name.endsWith("_SECRET")||name.endsWith("_KEY")))delete env[name];
}
const child=spawn(process.execPath,["node_modules/@react-router/serve/bin.js",
  "./build/server/index.js"],{cwd:process.cwd(),env,stdio:"ignore"});
let checked=0;
try{
  const origin="http://127.0.0.1:"+port;
  let ready=false;
  for(let i=0;i<80;i++){
    if(child.exitCode!==null)throw new Error("Server exited during startup");
    try{const r=await fetch(origin+"/"+slugs[0]+"/privacy");
      if(r.status===200){ready=true;break;}}catch{}
    await sleep(100);
  }
  assert.ok(ready,"Server did not start");
  const errors=[];
  for(const slug of slugs) {
    for(const page of ["","privacy","terms","support","review-demo"]) {
      const path="/"+slug+"/"+page;
      const response=await fetch(origin+path);
      if(response.status!==200)errors.push(path+" status="+response.status);
      checked++;
    }
  }
  assert.deepEqual(errors,[],"Broken public Shopify pages (possible reviewer 500)");
  console.log("PASS",slugs.length,"known Shopify apps,",checked,"public endpoints, no production credentials");
}finally{
  child.kill("SIGTERM");
  await sleep(250);
  if(child.exitCode===null)child.kill("SIGKILL");
}
