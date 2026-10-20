import type {ActionFunctionArgs, LoaderFunctionArgs} from "react-router";
import {getShopify} from "../../multi-shopify.server";

const AUDIT_QUERY = `#graphql
  query SeoAudit {
    shop { name }
    products(first: 50, sortKey: UPDATED_AT, reverse: true) {
      nodes {
        id
        title
        description
        vendor
        productType
        seo { title description }
        media(first: 10) {
          nodes {
            ... on MediaImage {
              id
              alt
              mediaContentType
            }
          }
        }
      }
    }
  }`;

type ProductRow = {  id: string;
  title: string;
  description: string;
  vendor: string;
  productType: string;
  seo: { title?: string | null; description?: string | null };
  media: { nodes: Array<{ id?: string; alt?: string | null; mediaContentType?: string }> };
};

function clean(s: string | null | undefined) {
  return String(s || "").replace(/\s+/g, " ").trim();
}
function cut(s: string, n: number) {
  const v = clean(s);
  return v.length <= n ? v : v.slice(0, Math.max(0, n - 1)).trimEnd() + "…";
}
function auditProduct(p: ProductRow) {
  const missingSeoTitle = !clean(p.seo?.title);
  const missingSeoDescription = !clean(p.seo?.description);
  const missingAlt = (p.media?.nodes || []).filter((m) => m?.id && !clean(m.alt)).length;
  return { missingSeoTitle, missingSeoDescription, missingAlt };
}
function suggestedDescription(p: ProductRow) {
  const fromBody = clean(p.description);
  if (fromBody) return cut(fromBody, 155);
  const bits = [p.title, p.vendor ? `by ${p.vendor}` : "", p.productType || ""].filter(Boolean);
  return cut(`${bits.join(" ")}. Shop this product online.`, 155);
}

async function fetchAudit(admin: any) {  const response = await admin.graphql(AUDIT_QUERY);
  const json = await response.json();
  if (!response.ok || json.errors?.length || !json.data?.products) {
    throw new Error("Shopify product audit unavailable");
  }
  return {
    shopName: String(json.data?.shop?.name || "Store"),
    products: (json.data?.products?.nodes || []) as ProductRow[],
  };
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin } = await getShopify('pal-seo-bulk-fixer').authenticate.admin(request);
  const { shopName, products } = await fetchAudit(admin);
  const rows = products.map((p) => ({ product: p, audit: auditProduct(p) }));
  const summary = rows.reduce(
    (a, r) => ({
      products: a.products + 1,
      productsWithIssues: a.productsWithIssues + (r.audit.missingSeoTitle || r.audit.missingSeoDescription || r.audit.missingAlt ? 1 : 0),
      missingSeoTitles: a.missingSeoTitles + (r.audit.missingSeoTitle ? 1 : 0),
      missingSeoDescriptions: a.missingSeoDescriptions + (r.audit.missingSeoDescription ? 1 : 0),
      missingAltTexts: a.missingAltTexts + r.audit.missingAlt,
    }),
    { products: 0, productsWithIssues: 0, missingSeoTitles: 0, missingSeoDescriptions: 0, missingAltTexts: 0 },
  );
  const issueUnits = summary.missingSeoTitles + summary.missingSeoDescriptions + summary.missingAltTexts;
  const possibleUnits = Math.max(1, summary.products * 2 + products.reduce((n, p) => n + (p.media?.nodes?.length || 0), 0));
  const score = Math.max(0, Math.round(100 - (issueUnits / possibleUnits) * 100));
  return { shopName, rows, summary, score };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin } = await getShopify('pal-seo-bulk-fixer').authenticate.admin(request);
  const form = await request.formData();
  if (String(form.get("intent") || "") !== "fixMissing") return { ok: false, error: "Unknown action" };
  let shopName: string;
  let products: ProductRow[];
  try {
    ({ shopName, products } = await fetchAudit(admin));
  } catch {
    return { ok: false, error: "Product audit temporarily unavailable. Please retry.", errors: [] as string[] };
  }
  let productsUpdated = 0;
  let seoFieldsFixed = 0;
  let altTextsFixed = 0;
  const errors: string[] = [];

  for (const p of products) {
    const issue = auditProduct(p);
    if (!issue.missingSeoTitle && !issue.missingSeoDescription && issue.missingAlt === 0) continue;

    if (issue.missingSeoTitle || issue.missingSeoDescription) {
      const seo = {
        ...(issue.missingSeoTitle ? { title: cut(`${p.title} | ${shopName}`, 60) } : {}),
        ...(issue.missingSeoDescription ? { description: suggestedDescription(p) } : {}),
      };
      const response = await admin.graphql(
        `#graphql
          mutation UpdateSeo($product: ProductUpdateInput!) {
            productUpdate(product: $product) {
              product { id }
              userErrors { field message }
            }
          }`,
        { variables: { product: { id: p.id, seo } } },
      );
      const json:any = await response.json();
      const userErrors = json.data?.productUpdate?.userErrors || [];
      if (!response.ok || json.errors?.length || !json.data?.productUpdate || userErrors.length) {
        errors.push(`${p.title}: ${userErrors.map((e: any) => e.message).join("; ") || "SEO update was rejected"}`);
      } else {
        productsUpdated++;
        seoFieldsFixed += Number(issue.missingSeoTitle) + Number(issue.missingSeoDescription);
      }
    }

    const media = (p.media?.nodes || []).filter((m) => m?.id && !clean(m.alt));
    if (media.length) {      const updates = media.map((m, index) => ({
        id: m.id,
        alt: cut(`${p.title} product image${index ? ` ${index + 1}` : ""}`, 125),
      }));
      const response = await admin.graphql(
        `#graphql
          mutation UpdateAlt($files: [FileUpdateInput!]!) {
            fileUpdate(files: $files) {
              files { id alt }
              userErrors { field message }
            }
          }`,
        { variables: { files: updates } },
      );
      const json:any = await response.json();
      const mediaErrors = json.data?.fileUpdate?.userErrors || [];
      if (!response.ok || json.errors?.length || !json.data?.fileUpdate || mediaErrors.length) {
        errors.push(`${p.title}: ${mediaErrors.map((e: any) => e.message).join("; ") || "Image alt text update was rejected"}`);
      } else {
        altTextsFixed += updates.length;
        if (!issue.missingSeoTitle && !issue.missingSeoDescription) productsUpdated++;
      }
    }
  }

  return {
    ok: errors.length === 0,
    productsUpdated,
    seoFieldsFixed,
    altTextsFixed,
    errors: errors.slice(0, 8),
  };
};

