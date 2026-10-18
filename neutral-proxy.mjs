// A neutral, review-compliant host for two Shopify apps. Existing stage3
// routes continue to run through the original React Router service unchanged.
import http from "node:http";
import { pricingWelcomeLocation } from "./pricing-welcome.mjs";
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
 "/pal-shipping-weight-integrity-guard/", "/pal-inventory-availability-guard/", "/pal-seo-fallback-readiness-guard/",
 "/pal-vendor-name-consistency-guard/", "/pal-variant-sale-guard/",
 "/pal-import-row-integrity-guard/",
 "/pal-feed-readiness-guard/",
 "/pal-variant-order-guard/",
 "/pal-variant-image-guard/",
 "/pal-title-length-guard/",
 "/pal-title-word-count-guard/",
 "/pal-title-digit-guard/",
 "/pal-title-trailing-mark-guard/",
 "/pal-title-leading-space-guard/",

 "/pal-barcode-format-guard/",
 "/pal-barcode-length-guard/",
 "/pal-barcode-space-guard/",
 "/pal-compare-price-equal-guard/",
 "/pal-compare-price-format-guard/",
 "/pal-compare-zero-guard/",
 "/pal-description-bold-guard/",
 "/pal-description-broken-link-guard/",
 "/pal-description-email-guard/",
 "/pal-description-empty-anchor-guard/",
 "/pal-description-empty-guard/",
 "/pal-description-heading-guard/",
 "/pal-description-image-count-guard/",
 "/pal-description-list-guard/",
 "/pal-description-long-guard/",
 "/pal-description-phone-guard/",
 "/pal-description-script-guard/",
 "/pal-description-short-guard/",
 "/pal-description-uppercase-guard/",
 "/pal-handle-digit-tail-guard/",
 "/pal-handle-format-guard/",
 "/pal-handle-length-guard/",
 "/pal-option-name-length-guard/",
 "/pal-option-value-case-guard/",
 "/pal-option-value-empty-guard/",
 "/pal-option-value-space-guard/",
 "/pal-price-precision-guard/",
 "/pal-tag-duplicate-guard/",
 "/pal-tag-numeric-guard/",
 "/pal-tag-symbol-guard/",
 "/pal-tag-uppercase-guard/",
 "/pal-tag-whitespace-guard/",
 "/pal-type-empty-guard/",
 "/pal-type-length-guard/",
 "/pal-variant-empty-guard/",
 "/pal-variant-sku-case-guard/",
 "/pal-variant-sku-length-guard/",
 "/pal-variant-sku-numeric-guard/",
 "/pal-variant-sku-space-guard/",
 "/pal-variant-sku-symbol-guard/",
 "/pal-variant-title-delimiter-guard/",
 "/pal-variant-title-length-guard/",
 "/pal-vendor-empty-guard/",
 "/pal-vendor-length-guard/",
 "/pal-vendor-symbol-guard/",
 "/pal-barcode-integrity-guard/",
 "/pal-tag-consistency-guard/",
 "/pal-product-type-consistency-guard/",
 "/pal-option-name-consistency-guard/",
 "/pal-option-value-consistency-guard/",
 "/pal-inventory-policy-consistency-guard/",
 "/pal-variant-tax-flag-guard/",
 "/pal-empty-collection-guard/",
 "/pal-sku-format-consistency-guard/",
 "/pal-collection-coverage-guard/",
 "/pal-variant-shipping-policy-guard/",
 "/pal-inventory-location-consistency-guard/",
 "/pal-unit-cost-coverage-guard/",
 "/pal-customs-data-readiness-guard/",
 "/pal-selling-plan-coverage-guard/",
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
        /^\/(?:pal-collection-(?:image-ratio|sort)-guard|pal-product-image-alt-guard|pal-active-product-age-guard|pal-shipping-weight-integrity-guard|pal-inventory-availability-guard)\/review-screencast\.mp4$/.test(pathname) &&
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
  // This public service is the review proxy. Its routing readiness should not
  // depend on the separate local legacy app/database migration starting first.
  // Slugged review routes go to the independently hosted gateway.
  if (parsed.pathname === "/health" && ["GET","HEAD"].includes(request.method||"GET")) {
    response.writeHead(200,{"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
    response.end(request.method==="HEAD" ? undefined : "review proxy ready\n");
    return;
  }
  // Public reviewer evidence is a static, application-specific document;
  // serve this exact route locally without altering other proxy routing.
  if (parsed.pathname === "/pal-collection-image-ratio-guard/review-evidence" &&
      ["GET","HEAD"].includes(request.method || "GET")) {
    const proof=path.resolve("review-proof/ratio-shopify-billing-evidence-20261018.html");
    if (!fs.existsSync(proof)) {
      response.writeHead(503,{"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
      response.end("Review evidence is temporarily unavailable");
      return;
    }
    const info=fs.statSync(proof);
    response.writeHead(200,{
      "content-type":"text/html; charset=utf-8",
      "content-length":info.size,
      "cache-control":"public, max-age=300",
      "x-content-type-options":"nosniff",
      "content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'"
    });
    if (request.method === "HEAD")response.end();
    else fs.createReadStream(proof).pipe(response);
    return;
  }
  // Reviewer evidence for verified Barcode Integrity Guard app launch.
  if (parsed.pathname === "/pal-barcode-integrity-guard/review-evidence" &&
      ["GET","HEAD"].includes(request.method || "GET")) {
    const proof=path.resolve("review-proof/barcode-integrity-20261018.html");
    if (!fs.existsSync(proof)) {
      response.writeHead(503,{"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
      response.end("Review evidence unavailable");
      return;
    }
    const info=fs.statSync(proof);
    response.writeHead(200,{
      "content-type":"text/html; charset=utf-8",
      "content-length":info.size,
      "cache-control":"public, max-age=300",
      "x-content-type-options":"nosniff",
      "content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'"
    });
    if (request.method === "HEAD")response.end();
    else fs.createReadStream(proof).pipe(response);
    return;
  }
  // Verified Vendor Name Guard app launch evidence, isolated to its review URL.
  if (parsed.pathname === "/pal-vendor-name-consistency-guard/review-evidence" &&
      ["GET","HEAD"].includes(request.method || "GET")) {
    const proof=path.resolve("review-proof/vendor-name-20261018.html");
    if (!fs.existsSync(proof)) {
      response.writeHead(503,{"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
      response.end("Review evidence unavailable"); return;
    }
    const info=fs.statSync(proof);
    response.writeHead(200,{
      "content-type":"text/html; charset=utf-8",
      "content-length":info.size,
      "cache-control":"public, max-age=300",
      "x-content-type-options":"nosniff",
      "content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'"
    });
    if (request.method === "HEAD")response.end();
    else fs.createReadStream(proof).pipe(response);
    return;
  }
  // Reviewer-specific static proof: exact allowlisted app IDs only.
  // Do not proxy proof pages through an authenticated merchant backend.
  const threeReviewProofs={
    "/pal-option-value-consistency-guard/review-evidence":"review-proof/option-value-20261018.html",
    "/pal-product-type-consistency-guard/review-evidence":"review-proof/product-type-20261018.html",
    "/pal-variant-shipping-policy-guard/review-evidence":"review-proof/variant-shipping-20261018.html"
  };
  const selectedReviewProof=threeReviewProofs[parsed.pathname];
  if (selectedReviewProof && ["GET","HEAD"].includes(request.method||"GET")) {
    const proof=path.resolve(selectedReviewProof);
    if(!fs.existsSync(proof)){
      response.writeHead(503,{"content-type":"text/plain; charset=utf-8","cache-control":"no-store"});
      response.end("Evidence temporarily unavailable");return;
    }
    const stat=fs.statSync(proof);
    response.writeHead(200,{
      "content-type":"text/html; charset=utf-8",
      "content-length":stat.size,
      "cache-control":"public, max-age=300",
      "x-content-type-options":"nosniff",
      "content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'"
    });
    if(request.method==="HEAD")response.end();
    else fs.createReadStream(proof).pipe(response);
    return;
  }
  // Public, read-only app-specific reviewer proof pages, not a replacement
  // for actual OAuth/embedded behavior or the existing proxy routes.
  const pausedProofPages = new Map([
    ['/pal-variant-shipping-policy-guard/review-evidence', 'review-proof/pal-variant-shipping-policy-guard-app-ui-20261018.html'],
    ['/pal-option-value-consistency-guard/review-evidence', 'review-proof/pal-option-value-consistency-guard-app-ui-20261018.html'],
    ['/pal-product-type-consistency-guard/review-evidence', 'review-proof/pal-product-type-consistency-guard-app-ui-20261018.html'],
  ]);
  if (["GET","HEAD"].includes(request.method || "GET") &&
      pausedProofPages.has(parsed.pathname)) {
    const proof=path.resolve(pausedProofPages.get(parsed.pathname));
    if (!fs.existsSync(proof)) {
      response.writeHead(503,{"content-type":"text/plain; charset=utf-8"});
      response.end("Review evidence temporarily unavailable");
      return;
    }
    const meta=fs.statSync(proof);
    response.writeHead(200,{
      "content-type":"text/html; charset=utf-8",
      "content-length":meta.size,
      "cache-control":"public, max-age=300",
      "x-content-type-options":"nosniff",
      "content-security-policy":"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'"
    });
    if (request.method === "HEAD") response.end();
    else fs.createReadStream(proof).pipe(response);
    return;
  }
  // Pricing welcome links must remain inside the exact reviewed app's path.
  // The destination still enforces Shopify authentication and session checks.
  if (["GET", "HEAD"].includes(request.method || "GET")) {
    const welcomeLocation = pricingWelcomeLocation(parsed.pathname, parsed.search, appPrefixes);
    if (welcomeLocation) {
      response.writeHead(302, { location: welcomeLocation, "cache-control": "no-store" });
      response.end();
      return;
    }
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
          // Shopify Admin can launch paid embedded apps at /app without
          // their slug. Route by OAuth audience, then verify auth upstream.
          "7b25b2746b7ca1ee8f6410267d7818c3":"/pal-collection-image-ratio-guard/app",
          "140fa929190b1abad51afb4b2dca8c5a":"/pal-collection-sort-guard/app",
          "b037098012b7c5d3daaf3162aab379df":"/pal-product-image-alt-guard/app",
          "f929810ee3a2fd0a979f9e45086635f7":"/pal-active-product-age-guard/app",
          "97deccb701377154727b76db4d7009aa":"/pal-variant-price-range-guard/app",
          "6ef199436a0be965d3d9cc3c5171dcdf":"/pal-zero-price-variant-guard/app",
          "32a3186a1e08a6ddb8adc4475f1b4c78":"/pal-product-template-guard/app",
          "517d7cad2cdc964792a0508b74501af0":"/pal-category-attribute-coverage-guard/app",
          "e4061fcb3b6aa33738e8aa3940afb0df":"/pal-product-media-count-guard/app",
          "76701835db46026187b611c70999b458":"/pal-stale-draft-product-guard/app",
          "617efcd24f2f797b19a95e8174de66e0":"/pal-product-description-guard/app",
          "31dc7aabbef154e172be87a234c48ce1":"/pal-collection-content-guard/app",
          "c6b005cee3edc110043f3a6a66b20b28":"/pal-shipping-weight-integrity-guard/app",
          "13d6c4df2adb508062fafa3161aff790":"/pal-inventory-availability-guard/app",
          "e2a4144f9b935d5b903f864b2ebb3e0c":"/pal-seo-fallback-readiness-guard/app",
          "ef2063aa4863f43ef1c33be84c1c68c0":"/pal-vendor-name-consistency-guard/app",
          "24992bb244fe201225321dc9c2f9e02c":"/pal-variant-sale-guard/app",
          "4034c9a54de58adda0cb3138fc442ff1":"/pal-import-row-integrity-guard/app",
          "f68f26c1cb5d2dd1d5ef10562f79c10f":"/pal-feed-readiness-guard/app",
          "3514c58d2fe75a7258dfe6343488ed62":"/pal-variant-order-guard/app",
          "73a6c1d5827e8d65d14f89a96af00b45":"/pal-variant-image-guard/app",
          "526f1173e69533a021b0611c8854b196":"/pal-title-length-guard/app",
          "d4e746e3165958a062cefd84198fd6c3":"/pal-title-word-count-guard/app",
          "5455b1bf44686b310cd80fb5538d098c":"/pal-title-digit-guard/app",
          "ef01f26be3940315d1e04bbea71eb8c5":"/pal-title-trailing-mark-guard/app",
          "b63024444661f58d6c24ab88749753c7":"/pal-title-leading-space-guard/app",

          "aa29ef4b9c8636cd42fdd5ba3abbbded":"/pal-barcode-format-guard/app",
          "cdbc7bfe6422ec3254fdb6fda5cb1b69":"/pal-barcode-length-guard/app",
          "0c91dd813c221baab2780afbce49a26d":"/pal-barcode-space-guard/app",
          "7eb31e339741c8a27b0cc1c4dfc4916c":"/pal-compare-price-equal-guard/app",
          "3a6852d6d46216d097acc80b15ec2119":"/pal-compare-price-format-guard/app",
          "ebf6cce79650bf235fa404d5ef92d11a":"/pal-compare-zero-guard/app",
          "ef3ff12cc4c294cddf2f3b5852c44583":"/pal-description-bold-guard/app",
          "19c5e390fd48c5c036bf8a7f5b8135ac":"/pal-description-broken-link-guard/app",
          "f6dd6b8348eee9f7c4eba2713e26d514":"/pal-description-email-guard/app",
          "1b4fe0e50c1727c34871212f16331f41":"/pal-description-empty-anchor-guard/app",
          "ddf3f7b789b062bcd2ea41961608f328":"/pal-description-empty-guard/app",
          "88f1012f6303b0b613bd6d78ddb92233":"/pal-description-heading-guard/app",
          "1715cfa47a1a3067831ed6454f6d8baa":"/pal-description-image-count-guard/app",
          "29f8ead0474a95325992690c0eb735f8":"/pal-description-list-guard/app",
          "ca24c01af2e69ac521bf745472cb3537":"/pal-description-long-guard/app",
          "638826fadce2f39e3f376a60636377af":"/pal-description-phone-guard/app",
          "4db9d610f4edf8b4a3048b643b2efc3c":"/pal-description-script-guard/app",
          "610ffb983936b789f76e2a19ff5479f2":"/pal-description-short-guard/app",
          "575aeaa248445d13542f01d1c34464ab":"/pal-description-uppercase-guard/app",
          "3db04d0c3a470326a25d8d7c801defb3":"/pal-handle-digit-tail-guard/app",
          "2038502b92089081438651bf9e4565f0":"/pal-handle-format-guard/app",
          "5fd87fbea1bdcd26db5f6236b4356bfa":"/pal-handle-length-guard/app",
          "475bb448018eb5f257c059370ce17d6c":"/pal-option-name-length-guard/app",
          "ff6e54d410e142152726aa9c27c0460b":"/pal-option-value-case-guard/app",
          "62b81b329c524c133e678f53673335d6":"/pal-option-value-empty-guard/app",
          "ff2ec214a87e8d7f6789eebaaa1f1c24":"/pal-option-value-space-guard/app",
          "898c5978b47c2be2d5de115a6b9c5005":"/pal-price-precision-guard/app",
          "771d0d3b8391008471eaf13ba3886a70":"/pal-tag-duplicate-guard/app",
          "fc6e3a0c072a01badcb2c403374c4703":"/pal-tag-numeric-guard/app",
          "d3c94f7de6bfa082d853a55459e2d189":"/pal-tag-symbol-guard/app",
          "e255d8250467304e08c6ff4602b65d3d":"/pal-tag-uppercase-guard/app",
          "be7c31ae52c7ac0c5abfe43978f7a72f":"/pal-tag-whitespace-guard/app",
          "36c342fa7c499770e2a15566ce6e90d7":"/pal-type-empty-guard/app",
          "e4dbbc55abb45b1ffc655bb78e1954a1":"/pal-type-length-guard/app",
          "acce6a131174237ca9469c16b76c5a2e":"/pal-variant-empty-guard/app",
          "f048a2c07ed17ae8d1f565eaba93f202":"/pal-variant-sku-case-guard/app",
          "abbd367598bc823895a7278dc8621816":"/pal-variant-sku-length-guard/app",
          "2e11383e7c980235d5fef3c653d5a866":"/pal-variant-sku-numeric-guard/app",
          "40aaae070a541902cf0a3ff57f1bdde8":"/pal-variant-sku-space-guard/app",
          "3d5c021df5bbfd09be7ad456d7d1c66e":"/pal-variant-sku-symbol-guard/app",
          "2fb5cf714b9a6fd74a64524aad912273":"/pal-variant-title-delimiter-guard/app",
          "c0e7694dfd1cab30b42a02fd6a7ba791":"/pal-variant-title-length-guard/app",
          "d9140427de55f8f7c324760905d4fc7e":"/pal-vendor-empty-guard/app",
          "eedc841a4527157a210142270df82fbf":"/pal-vendor-length-guard/app",
          "819fd4c15500700c42d593971c914cab":"/pal-vendor-symbol-guard/app",
          "d605dbbe6d5d267e841b69d7a0bad95a":"/pal-barcode-integrity-guard/app",
          "ff61224be0209366181a0d3503c9dc78":"/pal-tag-consistency-guard/app",
          "97db88e20fb8bdbb18220650ce695dc7":"/pal-product-type-consistency-guard/app",
          "806bd56efa9629ad779ea941ca1b8288":"/pal-option-name-consistency-guard/app",
          "2f0fca750aef32ce0d8b12fb25617f4e":"/pal-option-value-consistency-guard/app",
          "b8fd518d96c479c0fe8fc47ede9d85df":"/pal-inventory-policy-consistency-guard/app",
          "397f931af1844a7fcbb6be57c4924fc7":"/pal-variant-tax-flag-guard/app",
          "54ef28681e7dfb6bcc74826ca559ee67":"/pal-empty-collection-guard/app",
          "abf4d3dac9f1b19f33318704a3e76735":"/pal-sku-format-consistency-guard/app",
          "042cf3bdea0340686971688221d468fa":"/pal-collection-coverage-guard/app",
          "e831e40715bda8c781756b7303aeda45":"/pal-variant-shipping-policy-guard/app",
          "36c47b156c89dceca1787af24f64db6a":"/pal-inventory-location-consistency-guard/app",
          "adca0c82527583faf2c61e1ccf663b5d":"/pal-unit-cost-coverage-guard/app",
          "2ab13f79277dd4c361c9338166065bf3":"/pal-customs-data-readiness-guard/app",
          "4a3cfd77297a6b01ee63728974c817d6":"/pal-selling-plan-coverage-guard/app",
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
