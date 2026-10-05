export type ProductInput = {
  id: string; legacyResourceId: string; title: string; handle: string;
  status: string; updatedAt: string; descriptionHtml: string;
  images: { nodes: Array<{ altText: string | null }> };
  media: { nodes: Array<{ mediaContentType: string }> };
};
export type Finding = { product: ProductInput; reason: string; detail: string };
export type AuditResult = { products: ProductInput[]; findings: Finding[]; cleanCount: number; mode: string };
const norm=(s:string)=>s.trim().toLowerCase().replace(/\s+/g," ");
const plain=(s:string)=>s.replace(/<[^>]*>/g," ").replace(/\s+/g," ").trim();
export function auditProducts(products: ProductInput[], mode: string, now=new Date("2026-10-02T16:30:00+09:00")): AuditResult {
  const findings: Finding[] = [];
  const titleCounts=new Map<string,number>();
  for(const p of products){const n=norm(p.title);titleCounts.set(n,(titleCounts.get(n)||0)+1);}
  for(const product of products){
    if(mode==="image_alt"){
      const alts=product.images.nodes.map(x=>norm(x.altText||""));
      const missing=alts.filter(x=>!x).length;
      const seen=new Set<string>(); let dup=0;
      for(const a of alts){if(!a)continue;if(seen.has(a))dup++;seen.add(a);}
      if(missing) findings.push({product,reason:"Missing alt text",detail:missing+" image(s) without alt text"});
      else if(dup) findings.push({product,reason:"Repeated alt text",detail:dup+" repeated alt-text value(s)"});
    } else if(mode==="title"){
      const t=product.title.trim(), letters=t.replace(/[^A-Za-z]/g,"");
      if(t.length<10) findings.push({product,reason:"Short title",detail:t.length+" characters"});
      else if(t.length>80) findings.push({product,reason:"Long title",detail:t.length+" characters"});
      else if(letters.length>=5 && letters===letters.toUpperCase()) findings.push({product,reason:"All-caps title",detail:"Review title casing"});
      else if((titleCounts.get(norm(t))||0)>1) findings.push({product,reason:"Duplicate normalized title",detail:"Another product uses the same normalized title"});
    } else if(mode==="description"){
      const n=plain(product.descriptionHtml||"").length;
      if(n===0) findings.push({product,reason:"Missing description",detail:"No product description text"});
      else if(n<80) findings.push({product,reason:"Short description",detail:n+" text characters"});
    } else if(mode==="stale_draft"){
      if(product.status==="DRAFT"){
        const days=Math.floor((now.getTime()-new Date(product.updatedAt).getTime())/86400000);
        if(days>=90) findings.push({product,reason:"Stale draft",detail:days+" days since last update"});
      }
    } else if(mode==="media_count"){
      const n=product.media.nodes.length;
      if(n===0) findings.push({product,reason:"No media",detail:"No product media found"});
      else if(n<2) findings.push({product,reason:"Low media coverage",detail:n+" media item"});
    }
  }
  const flagged=new Set(findings.map(x=>x.product.id));
  return {products,findings,cleanCount:products.length-flagged.size,mode};
}
export function productAdminUrl(shopDomain:string,id:string){const store=shopDomain.replace(/\.myshopify\.com$/i,"");return "https://admin.shopify.com/store/"+encodeURIComponent(store)+"/products/"+encodeURIComponent(id);}
const cell=(v:string|number)=>'"'+String(v??"").replaceAll('"','""')+'"';
export function buildCsv(a:AuditResult,shopDomain:string){const rows=[["Product","Issue","Detail","Admin link"],...a.findings.map(f=>[f.product.title,f.reason,f.detail,productAdminUrl(shopDomain,f.product.legacyResourceId)])];return "\uFEFF"+rows.map(r=>r.map(cell).join(",")).join("\n");}
