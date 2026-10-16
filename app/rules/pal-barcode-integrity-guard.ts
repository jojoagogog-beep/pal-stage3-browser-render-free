export const appMeta = {
  shortName: "Barcode Integrity Guard",
  exportSlug: "barcode-integrity",
  readonlyLabel: "Read-only · Catalog integrity",
  eyebrow: "CATALOG QA / REVIEW",
  headline: "Find reused and missing barcodes across product variants.",
  lead: "Review barcodes shared by different products and variants missing a barcode when their siblings have one.",
  sidebarHelp: "Focus on barcode collisions and missing sibling identifiers.",
  readOnlyNote: "PAL never invents, edits, or assigns barcode values.",
  panelTitle: "Barcode integrity findings",
  emptyCopy: "No barcode collisions or missing sibling barcodes were detected in this product batch.",
  statusCopy: "Results are based on the currently loaded product batch.",
} as const;

export type Variant = {
  id: string; title: string; sku: string | null; barcode: string | null;
  price: string; compareAtPrice: string | null;
  selectedOptions: Array<{name: string; value: string}>;
};
export type Product = {
  id: string; title: string; vendor: string; productType: string;
  tags: string[]; handle: string; descriptionHtml: string;
  variants: {nodes: Variant[]};
};
export type Finding = {
  productId: string; productTitle: string; rule: "issue";
  evidence: string; detail: string;
};
export type Audit = {products: number; findings: Finding[]; skipped: string[]};

export const rules = {issue:{
  label:"Barcode integrity review",
  priority:"High",
  advice:"Confirm the manufacturer's barcode and update only the correct variant in Shopify admin. Never invent a code.",
}} as const;

const cleaned = (s:string|null|undefined) => (s||"").trim();
const key = (s:string|null|undefined) => cleaned(s).toLocaleUpperCase("en-US");

export function auditCatalog(products:Product[]):Audit {
  const findings:Finding[]=[];
  const byBarcode=new Map<string,Array<{p:Product;v:Variant}>>();
  for(const p of products){
    const siblingCount=p.variants.nodes.filter(v=>Boolean(key(v.barcode))).length;
    for(const v of p.variants.nodes) {
      const b=key(v.barcode);
      if(b){
        const group=byBarcode.get(b)||[];
        group.push({p,v});
        byBarcode.set(b,group);
      } else if(siblingCount>0) {
        findings.push({
          productId:p.id,productTitle:p.title,rule:"issue",
          evidence:`Variant: ${v.title} · ${siblingCount} sibling(s) have barcodes`,
          detail:"This variant is missing a barcode while at least one sibling variant has one.",
        });
      }
    }
  }
  for(const [barcode,items] of byBarcode){
    const distinctProducts=new Set(items.map(x=>x.p.id));
    if(distinctProducts.size<2) continue;
    for(const {p,v} of items){
      findings.push({
        productId:p.id,productTitle:p.title,rule:"issue",
        evidence:`Barcode: ${cleaned(v.barcode)} · Variant: ${v.title}`,
        detail:`The barcode is also used by variants of ${distinctProducts.size-1} other product(s) in this batch.`,
      });
    }
  }
  findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle)||a.evidence.localeCompare(b.evidence));
  return {products:products.length,findings,skipped:[]};
}

const csv=(value:string)=>{
  const v=/^[\s]*[=+@\-\t\r\n]/.test(value)?"'"+value:value;
  return '"'+v.replace(/"/g,'""')+'"';
};
export function buildCsv(findings:Finding[]):string {
  const rows=[
    ["Priority","Product","Product ID","Issue","Evidence","Recommendation"],
    ...findings.map(f=>["Review",f.productTitle,f.productId,rules.issue.label,f.evidence,rules.issue.advice])
  ];
  return "\uFEFF"+rows.map(r=>r.map(v=>csv(String(v))).join(",")).join("\r\n");
}
