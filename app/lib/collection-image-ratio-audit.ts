export type CollectionInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  handle: string;
  image: null | {
    width: number;
    height: number;
  };
};

export type AuditedCollection = CollectionInput & {
  ratio: number | null;
  ratioLabel: string;
  isOutlier: boolean;
};

export type AuditResult = {
  collections: AuditedCollection[];
  withImages: AuditedCollection[];
  missingImages: AuditedCollection[];
  outliers: AuditedCollection[];
  dominantRatioLabel: string | null;
  summary: {
    collectionsScanned: number;
    collectionsWithImages: number;
    missingImages: number;
    ratioGroups: number;
    outliers: number;
  };
};

function near(a: number, b: number, tolerance = 0.04) {
  return Math.abs(a - b) <= tolerance;
}

export function ratioLabel(width: number, height: number) {
  if (!width || !height) return "Unknown";
  const r = width / height;
  if (near(r, 1)) return "1:1";
  if (near(r, 4 / 3)) return "4:3";
  if (near(r, 3 / 2)) return "3:2";
  if (near(r, 16 / 9)) return "16:9";
  if (near(r, 3 / 4)) return "3:4";
  if (near(r, 2 / 3)) return "2:3";
  if (near(r, 9 / 16)) return "9:16";
  return r.toFixed(2) + ":1";
}

export function auditCollections(collections: CollectionInput[]): AuditResult {
  const initial = collections.map((collection) => {
    const ratio = collection.image
      ? collection.image.width / collection.image.height
      : null;
    return {
      ...collection,
      ratio,
      ratioLabel: collection.image
        ? ratioLabel(collection.image.width, collection.image.height)
        : "No image",
      isOutlier: false,
    };
  });

  const withImages = initial.filter((c) => c.image);
  const missingImages = initial.filter((c) => !c.image);
  const counts = new Map<string, number>();
  for (const c of withImages) {
    counts.set(c.ratioLabel, (counts.get(c.ratioLabel) || 0) + 1);
  }

  const dominantRatioLabel =
    [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;

  const collectionsWithFlags = initial.map((c) => ({
    ...c,
    isOutlier: Boolean(c.image && dominantRatioLabel && c.ratioLabel !== dominantRatioLabel),
  }));

  const flaggedWithImages = collectionsWithFlags.filter((c) => c.image);
  const flaggedMissing = collectionsWithFlags.filter((c) => !c.image);
  const outliers = collectionsWithFlags.filter((c) => c.isOutlier);

  return {
    collections: collectionsWithFlags,
    withImages: flaggedWithImages,
    missingImages: flaggedMissing,
    outliers,
    dominantRatioLabel,
    summary: {
      collectionsScanned: collections.length,
      collectionsWithImages: flaggedWithImages.length,
      missingImages: flaggedMissing.length,
      ratioGroups: counts.size,
      outliers: outliers.length,
    },
  };
}

function csvCell(value: string | number) {
  const s = String(value ?? "");
  return '"' + s.replaceAll('"', '""') + '"';
}

export function collectionAdminUrl(shopDomain: string, legacyResourceId: string) {
  const store = shopDomain.replace(/\.myshopify\.com$/i, "");
  return (
    "https://admin.shopify.com/store/" +
    encodeURIComponent(store) +
    "/collections/" +
    encodeURIComponent(legacyResourceId)
  );
}

export function buildDiagnosticCsv(audit: AuditResult, shopDomain: string) {
  const rows: Array<Array<string | number>> = [
    ["Collection", "Width", "Height", "Ratio group", "Dominant ratio", "Outlier", "Admin link"],
  ];

  for (const collection of audit.collections) {
    rows.push([
      collection.title,
      collection.image?.width ?? "",
      collection.image?.height ?? "",
      collection.ratioLabel,
      audit.dominantRatioLabel ?? "",
      collection.isOutlier ? "Yes" : "No",
      collectionAdminUrl(shopDomain, collection.legacyResourceId),
    ]);
  }

  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\n");
}
