export const PAGE_SIZE = 25;
export const MAX_PRODUCTS = 500;
export const MAX_METAFIELDS = 10;

export type MetafieldSelection = {
  namespace: string;
  key: string;
  identifier: string;
};

export type CatalogProduct = {
  id: string;
  title: string;
  tags: string[];
  options: Array<{ name: string; values: string[] }>;
  collections: { nodes: Array<{ id: string; title: string }> };
  selectedMetafields: Array<{
    identifier: string;
    type: string;
    value: string;
  } | null>;
};

export type AuditIssue = {
  kind: "Missing" | "Inconsistent";
  source: "Product option" | "Tag" | "Metafield";
  field: string;
  productId: string;
  productTitle: string;
  observedValue: string;
  suggestedValue: string;
  collections: string[];
};

export type DuplicateGroup = {
  source: AuditIssue["source"];
  field: string;
  variants: string[];
  suggestedValue: string;
  affectedProducts: number;
};

export type AuditResult = {
  issues: AuditIssue[];
  duplicateGroups: DuplicateGroup[];
  optionFields: string[];
  summary: {
    scannedProducts: number;
    affectedProducts: number;
    missingValues: number;
    inconsistentValues: number;
    duplicateGroups: number;
  };
};

const METAFIELD_PART = /^[A-Za-z0-9_-]+$/;

export function parseMetafieldSelections(raw: string): {
  selections: MetafieldSelection[];
  error?: string;
} {
  if (raw.length > 1_000) {
    return { selections: [], error: "Metafield settings are too long." };
  }

  const identifiers = [...new Set(raw.split(/[\s,]+/).map((value) => value.trim()).filter(Boolean))];
  if (identifiers.length > MAX_METAFIELDS) {
    return { selections: [], error: `Choose no more than ${MAX_METAFIELDS} metafields.` };
  }

  const selections: MetafieldSelection[] = [];
  for (const identifier of identifiers) {
    const parts = identifier.split(".");
    if (
      parts.length !== 2 ||
      !parts[0] ||
      !parts[1] ||
      parts[0].length > 255 ||
      parts[1].length > 64 ||
      !METAFIELD_PART.test(parts[0]) ||
      !METAFIELD_PART.test(parts[1])
    ) {
      return {
        selections: [],
        error: `“${identifier}” is invalid. Use namespace.key with letters, numbers, hyphens, or underscores.`,
      };
    }
    selections.push({ namespace: parts[0], key: parts[1], identifier });
  }

  return { selections };
}

export function normalizeFilterValue(value: string) {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

function cleanValue(value: string) {
  return value.normalize("NFKC").replace(/\s+/g, " ").trim();
}

function metafieldValues(field: CatalogProduct["selectedMetafields"][number]) {
  if (!field) return [];
  if (field.type.startsWith("list.")) {
    try {
      const parsed = JSON.parse(field.value);
      if (Array.isArray(parsed)) return parsed.map((value) => cleanValue(String(value))).filter(Boolean);
    } catch {
      return [];
    }
  }
  const value = cleanValue(field.value);
  return value ? [value] : [];
}

type Occurrence = {
  source: AuditIssue["source"];
  field: string;
  value: string;
  product: CatalogProduct;
};

function productCollections(product: CatalogProduct) {
  return product.collections.nodes.map((collection) => collection.title);
}

export function analyzeCatalog(
  products: CatalogProduct[],
  selections: MetafieldSelection[],
): AuditResult {
  const issues: AuditIssue[] = [];
  const occurrences: Occurrence[] = [];
  const optionPresence = new Map<string, number>();

  for (const product of products) {
    const seenOptions = new Set<string>();
    for (const option of product.options) {
      const name = cleanValue(option.name);
      const values = option.values.map(cleanValue).filter(Boolean);
      if (!name || (name.toLocaleLowerCase() === "title" && values.every((value) => value === "Default Title"))) {
        continue;
      }
      seenOptions.add(name);
      for (const value of values) occurrences.push({ source: "Product option", field: name, value, product });
      if (values.length === 0) {
        issues.push({
          kind: "Missing",
          source: "Product option",
          field: name,
          productId: product.id,
          productTitle: product.title,
          observedValue: "",
          suggestedValue: "Add a filter value",
          collections: productCollections(product),
        });
      }
    }
    for (const name of seenOptions) optionPresence.set(name, (optionPresence.get(name) || 0) + 1);

    const tags = product.tags.map(cleanValue).filter(Boolean);
    if (tags.length === 0) {
      issues.push({
        kind: "Missing",
        source: "Tag",
        field: "Product tags",
        productId: product.id,
        productTitle: product.title,
        observedValue: "",
        suggestedValue: "Review whether a filter tag is needed",
        collections: productCollections(product),
      });
    }
    for (const value of tags) occurrences.push({ source: "Tag", field: "Product tags", value, product });

    selections.forEach((selection, index) => {
      const field = product.selectedMetafields[index];
      const values = metafieldValues(field);
      if (values.length === 0) {
        issues.push({
          kind: "Missing",
          source: "Metafield",
          field: selection.identifier,
          productId: product.id,
          productTitle: product.title,
          observedValue: "",
          suggestedValue: "Add a filter value",
          collections: productCollections(product),
        });
      }
      for (const value of values) occurrences.push({ source: "Metafield", field: selection.identifier, value, product });
    });
  }

  // An option is treated as catalog-wide only when it appears on at least two
  // products and on 20% or more of the scanned catalog. This avoids flagging a
  // niche option as missing from every unrelated product.
  const commonOptions = [...optionPresence.entries()]
    .filter(([, count]) => count >= 2 && count / Math.max(1, products.length) >= 0.2)
    .map(([name]) => name)
    .sort((a, b) => a.localeCompare(b));

  for (const product of products) {
    const names = new Set(product.options.map((option) => cleanValue(option.name)));
    for (const field of commonOptions) {
      if (!names.has(field)) {
        issues.push({
          kind: "Missing",
          source: "Product option",
          field,
          productId: product.id,
          productTitle: product.title,
          observedValue: "",
          suggestedValue: "Review whether this option applies",
          collections: productCollections(product),
        });
      }
    }
  }

  const normalizedGroups = new Map<string, Occurrence[]>();
  for (const occurrence of occurrences) {
    const normalized = normalizeFilterValue(occurrence.value);
    if (!normalized) continue;
    const key = `${occurrence.source}\u0000${occurrence.field}\u0000${normalized}`;
    const group = normalizedGroups.get(key) || [];
    group.push(occurrence);
    normalizedGroups.set(key, group);
  }

  const duplicateGroups: DuplicateGroup[] = [];
  for (const group of normalizedGroups.values()) {
    const counts = new Map<string, number>();
    for (const occurrence of group) counts.set(occurrence.value, (counts.get(occurrence.value) || 0) + 1);
    if (counts.size < 2) continue;

    const variants = [...counts.keys()].sort((left, right) => left.localeCompare(right));
    const suggestedValue = [...counts.entries()].sort(
      (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
    )[0][0];
    const affectedProducts = new Set(group.map((occurrence) => occurrence.product.id)).size;
    duplicateGroups.push({
      source: group[0].source,
      field: group[0].field,
      variants,
      suggestedValue,
      affectedProducts,
    });

    const emitted = new Set<string>();
    for (const occurrence of group) {
      if (occurrence.value === suggestedValue) continue;
      const issueKey = `${occurrence.product.id}\u0000${occurrence.source}\u0000${occurrence.field}\u0000${occurrence.value}`;
      if (emitted.has(issueKey)) continue;
      emitted.add(issueKey);
      issues.push({
        kind: "Inconsistent",
        source: occurrence.source,
        field: occurrence.field,
        productId: occurrence.product.id,
        productTitle: occurrence.product.title,
        observedValue: occurrence.value,
        suggestedValue,
        collections: productCollections(occurrence.product),
      });
    }
  }

  issues.sort(
    (left, right) =>
      left.kind.localeCompare(right.kind) ||
      left.field.localeCompare(right.field) ||
      left.productTitle.localeCompare(right.productTitle),
  );
  duplicateGroups.sort((left, right) => left.field.localeCompare(right.field));

  return {
    issues,
    duplicateGroups,
    optionFields: commonOptions,
    summary: {
      scannedProducts: products.length,
      affectedProducts: new Set(issues.map((issue) => issue.productId)).size,
      missingValues: issues.filter((issue) => issue.kind === "Missing").length,
      inconsistentValues: issues.filter((issue) => issue.kind === "Inconsistent").length,
      duplicateGroups: duplicateGroups.length,
    },
  };
}

export function buildCatalogQuery(selections: MetafieldSelection[]) {
  const metafieldFields = selections
    .map(
      (selection, index) => `
        selectedMetafield${index}: metafield(
          namespace: ${JSON.stringify(selection.namespace)}
          key: ${JSON.stringify(selection.key)}
        ) { type value }`,
    )
    .join("\n");

  return `#graphql
    query FilterIntegrityCatalog($first: Int!, $after: String) {
      shop { name }
      products(first: $first, after: $after, sortKey: ID) {
        nodes {
          id
          title
          tags
          options { name values }
          collections(first: 10) { nodes { id title } }
          ${metafieldFields}
        }
        pageInfo { hasNextPage endCursor }
      }
    }`;
}

type AdminGraphqlClient = {
  graphql: (
    query: string,
    options: { variables: { first: number; after: string | null } },
  ) => Promise<Response>;
};

type ApiProductOption = { name?: unknown; values?: unknown[] };
type ApiCollection = { id?: unknown; title?: unknown };
type ApiMetafield = { type?: unknown; value?: unknown };
type ApiProduct = {
  id?: unknown;
  title?: unknown;
  tags?: unknown[];
  options?: ApiProductOption[];
  collections?: { nodes?: ApiCollection[] };
  [key: `selectedMetafield${number}`]: ApiMetafield | null | undefined;
};
type CatalogQueryResponse = {
  errors?: Array<{ message?: string }>;
  data?: {
    shop?: { name?: string };
    products?: {
      nodes?: ApiProduct[];
      pageInfo?: { hasNextPage?: boolean; endCursor?: string | null };
    };
  };
};

export async function scanCatalog(admin: AdminGraphqlClient, selections: MetafieldSelection[]) {
  const query = buildCatalogQuery(selections);
  const products: CatalogProduct[] = [];
  let shopName = "Store";
  let after: string | null = null;
  let hasNextPage = false;

  do {
    const response: Response = await admin.graphql(query, {
      variables: { first: PAGE_SIZE, after },
    });
    const json = (await response.json()) as CatalogQueryResponse;
    if (json.errors?.length) {
      throw new Error("Shopify could not return the catalog for this scan. Try again in a moment.");
    }

    shopName = String(json.data?.shop?.name || shopName);
    const connection = json.data?.products;
    for (const node of connection?.nodes || []) {
      products.push({
        id: String(node.id),
        title: String(node.title || "Untitled product"),
        tags: Array.isArray(node.tags) ? node.tags.map(String) : [],
        options: Array.isArray(node.options)
          ? node.options.map((option) => ({
              name: String(option.name || ""),
              values: Array.isArray(option.values) ? option.values.map(String) : [],
            }))
          : [],
        collections: {
          nodes: Array.isArray(node.collections?.nodes)
            ? node.collections.nodes.map((collection) => ({
                id: String(collection.id),
                title: String(collection.title || "Untitled collection"),
              }))
            : [],
        },
        selectedMetafields: selections.map((selection, index) => {
          const field = node[`selectedMetafield${index}`];
          return field
            ? { identifier: selection.identifier, type: String(field.type || ""), value: String(field.value || "") }
            : null;
        }),
      });
      if (products.length >= MAX_PRODUCTS) break;
    }

    hasNextPage = Boolean(connection?.pageInfo?.hasNextPage);
    after = connection?.pageInfo?.endCursor || null;
  } while (hasNextPage && after && products.length < MAX_PRODUCTS);

  return {
    shopName,
    products: products.slice(0, MAX_PRODUCTS),
    truncated: hasNextPage && products.length >= MAX_PRODUCTS,
    audit: analyzeCatalog(products.slice(0, MAX_PRODUCTS), selections),
  };
}
