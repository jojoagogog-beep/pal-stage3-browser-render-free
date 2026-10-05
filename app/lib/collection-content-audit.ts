export type CollectionInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  handle: string;
  description: string;
  image: null | { url: string; altText: string | null };
  seo: null | { title: string | null; description: string | null };
};

export type ContentGap = "Description" | "Image" | "SEO title" | "SEO description";

export type CollectionAudit = CollectionInput & {
  gaps: ContentGap[];
  ready: boolean;
};

export type AuditResult = {
  collections: CollectionAudit[];
  withGaps: CollectionAudit[];
  ready: CollectionAudit[];
  summary: {
    collectionsScanned: number;
    collectionsWithGaps: number;
    missingDescriptions: number;
    missingImages: number;
    missingSeoTitles: number;
    missingSeoDescriptions: number;
  };
};

function blank(value: string | null | undefined) {
  return !value || value.trim() === "";
}

export function auditCollections(collections: CollectionInput[]): AuditResult {
  const audited = collections.map((collection) => {
    const gaps: ContentGap[] = [];
    if (blank(collection.description)) gaps.push("Description");
    if (!collection.image?.url) gaps.push("Image");
    if (blank(collection.seo?.title)) gaps.push("SEO title");
    if (blank(collection.seo?.description)) gaps.push("SEO description");
    return { ...collection, gaps, ready: gaps.length === 0 };
  });
  const withGaps = audited.filter((collection) => !collection.ready);
  const ready = audited.filter((collection) => collection.ready);
  return {
    collections: audited,
    withGaps,
    ready,
    summary: {
      collectionsScanned: audited.length,
      collectionsWithGaps: withGaps.length,
      missingDescriptions: audited.filter((c) => c.gaps.includes("Description")).length,
      missingImages: audited.filter((c) => c.gaps.includes("Image")).length,
      missingSeoTitles: audited.filter((c) => c.gaps.includes("SEO title")).length,
      missingSeoDescriptions: audited.filter((c) => c.gaps.includes("SEO description")).length,
    },
  };
}

function csvCell(value: string | number) {
  const s = String(value ?? "");
  return '"' + s.replaceAll('"', '""') + '"';
}

export function collectionAdminUrl(shopDomain: string, legacyResourceId: string) {
  const store = shopDomain.replace(/\.myshopify\.com$/i, "");
  return "https://admin.shopify.com/store/" + encodeURIComponent(store) + "/collections/" + encodeURIComponent(legacyResourceId);
}

export function buildDiagnosticCsv(audit: AuditResult, shopDomain: string) {
  const rows = [
    ["Collection", "Missing fields", "Description", "Image URL", "SEO title", "SEO description", "Admin link"],
    ...audit.collections.map((collection) => [
      collection.title,
      collection.gaps.join(" | ") || "None",
      collection.description,
      collection.image?.url || "",
      collection.seo?.title || "",
      collection.seo?.description || "",
      collectionAdminUrl(shopDomain, collection.legacyResourceId),
    ]),
  ];
  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
