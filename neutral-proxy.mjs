// A neutral, review-compliant host for two Shopify apps. Existing stage3
// routes continue to run through the original React Router service unchanged.
import http from "node:http";
import https from "node:https";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import {spawn} from "node:child_process";

const appRoot = path.resolve("build/client");
const gateway = "pal-shopify-batch50-gateway.onrender.com";
const appPrefixes = [
 "/pal-collection-image-ratio-guard/", "/pal-collection-sort-guard/",
 "/pal-product-image-alt-guard/", "/pal-active-product-age-guard/",
 "/pal-variant-price-range-guard/", "/pal-zero-price-variant-guard/",
 "/pal-product-template-guard/", "/pal-category-attribute-coverage-guard/",
 "/pal-product-media-count-guard/", "/pal-stale-draft-product-guard/",
 "/pal-product-description-guard/", "/pal-collection-content-guard/",
 "/pal-shipping-weight-integrity-guard/"
];
const publicPort = Number(process.env.PORT || "10000");
const internalPort = 19731;
const child = spawn("npm", ["run", "docker-start"], {
  env: {...process.env, PORT: String(internalPort)},
  stdio: "inherit",
});
child.on("error", e=>{ console.error("ORIGINAL_APP_START_FAILED",e.message);process.exitCode=1;});
child.on("exit", (code,signal)=>{ console.error("ORIGINAL_APP_EXIT",code,signal);server.close();process.exitCode=code||1;});

function shouldSendToGateway(pathname, method) {
  if (appPrefixes.some(prefix=>pathname.startsWith(prefix))) {
    // Genuine review screencasts are packaged locally on the neutral host.
    if (["GET","HEAD"].includes(method) &&
        /^\/(?:pal-collection-(?:image-ratio|sort)-guard|pal-product-image-alt-guard|pal-active-product-age-guard|pal-shipping-weight-integrity-guard)\/review-screencast\.mp4$/.test(pathname) &&
        fs.existsSync(path.resolve(appRoot, "."+pathname))) return false;
    return true;
  }
  if (!["GET","HEAD"].includes(method)) return false;
  if (!pathname.startsWith("/assets/")) return false;
  let file;
  try {file=path.resolve(appRoot, "."+decodeURIComponent(pathname));} catch {return false;}
  if (!(file.startsWith(appRoot+path.sep))) return false;
  return !fs.existsSync(file);
}
function forward(request,response) {
  let parsed;
  try {parsed=new URL(request.url||"/","http://localhost");}catch{
    response.writeHead(400);response.end("Bad request");return;
  }
  // Shopify Admin can open the root /app path even when this embedded app was
  // released with a slugged app URL. Route *only* a known app audience to its
  // real backend, preserving the shared service and every other app.
  // The JWT payload is used solely as a routing hint, NOT authentication.
  // Shopify's authenticate.admin() verifies its signature and session.
  let routedPath=parsed.pathname;
  if (["GET","HEAD"].includes(request.method||"GET") && parsed.pathname==="/app") {
    try {
      const token=parsed.searchParams.get("id_token")||"";
      const parts=token.split(".");
      if (token.length<12000 && parts.length===3) {
        const payload=JSON.parse(Buffer.from(parts[1],"base64url").toString("utf8"));
        const appPaths={
          "f929810ee3a2fd0a979f9e45086635f7":"/pal-active-product-age-guard/app",
          "97deccb701377154727b76db4d7009aa":"/pal-variant-price-range-guard/app",
          "6ef199436a0be965d3d9cc3c5171dcdf":"/pal-zero-price-variant-guard/app",
          "32a3186a1e08a6ddb8adc4475f1b4c78":"/pal-product-template-guard/app",
          "517d7cad2cdc964792a0508b74501af0":"/pal-category-attribute-coverage-guard/app",
          "e4061fcb3b6aa33738e8aa3940afb0df":"/pal-product-media-count-guard/app",
          "76701835db46026187b611c70999b458":"/pal-stale-draft-product-guard/app",
          "617efcd24f2f797b19a95e8174de66e0":"/pal-product-description-guard/app",
          "31dc7aabbef154e172be87a234c48ce1":"/pal-collection-content-guard/app",
        };
        if (typeof payload.aud==="string" && Object.prototype.hasOwnProperty.call(appPaths,payload.aud)) {
          routedPath=appPaths[payload.aud];
        }
      }
    } catch { /* Invalid token: leave the default routing untouched. */ }
  }
  const merchant=shouldSendToGateway(routedPath,request.method||"GET");
  const target=merchant ? new URL(routedPath+parsed.search, "https://"+gateway)
    : new URL(parsed.pathname+parsed.search, "http://127.0.0.1:"+internalPort);
  const client=merchant?https:http;
  const headers={...request.headers,host:target.host};
  if(merchant){
    headers["x-forwarded-host"]=request.headers.host||"";
    headers["x-forwarded-proto"]="https";
  }
  const upstream=client.request(target,{method:request.method,headers},incoming=>{
    const h={...incoming.headers};
    if(merchant&&h.location){
      try {
        const dest=new URL(h.location,target);
        if(dest.hostname===gateway){
          dest.host=request.headers.host||dest.host;
          dest.protocol="https:";
          h.location=dest.toString();
        }
      }catch{}
    }
    if(merchant&&h["set-cookie"]){
      const cookies=Array.isArray(h["set-cookie"])?h["set-cookie"]:[h["set-cookie"]];
      h["set-cookie"]=cookies.map(v=>v.replace(/;\s*Domain=pal-shopify-batch50-gateway\.onrender\.com\b/ig,""));
    }
    response.writeHead(incoming.statusCode||502,h);
    incoming.pipe(response);
  });
  upstream.on("error",e=>{console.error("UPSTREAM_PROXY_FAILURE",merchant?"gateway":"local",e.code||e.message);if(!response.headersSent)response.writeHead(502);response.end("App temporarily unavailable");});
  request.on("aborted",()=>upstream.destroy());
  request.pipe(upstream);
}
const server=http.createServer(forward);
server.on("upgrade",(req,socket,head)=>{
  // Keep original app websocket-based workflows available.
  if(appPrefixes.some(prefix=>(req.url||"").startsWith(prefix))){socket.destroy();return;}
  const upstream=net.connect({host:"127.0.0.1",port:internalPort},()=>{
    const headers=Object.entries(req.headers).map(([k,v])=>k+": "+(Array.isArray(v)?v.join(", "):v)).join("\r\n");
    upstream.write((req.method||"GET")+" "+(req.url||"/")+" HTTP/1.1\r\n"+headers+"\r\n\r\n");
    if(head?.length)upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on("error",()=>socket.destroy());
  socket.on("error",()=>upstream.destroy());
});
server.listen(publicPort,"0.0.0.0",()=>console.log("PAL_NEUTRAL_PROXY_READY",publicPort,"LOCAL_CHILD",internalPort));
const stop=()=>{try{child.kill("SIGTERM");}catch{}server.close();};
process.on("SIGTERM",stop);process.on("SIGINT",stop);
