export type CategoryInput = {
  id: string;
  fullName: string;
};

export type DefinitionInput = {
  id: string;
  name: string;
  namespace: string;
  key: string;
  categoryValues: string[];
};

export type MetafieldInput = {
  namespace: string;
  key: string;
  value: string;
  type: string;
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  category: CategoryInput | null;
  metafields: MetafieldInput[];
};
export type AttributeAudit = DefinitionInput & {
  value: string | null;
  status: "Missing" | "Populated";
};

export type ProductAudit = ProductInput & {
  categoryHandle: string | null;
  attributes: AttributeAudit[];
  status: "No category" | "Incomplete" | "Complete" | "No applicable fields";
  missingAttributeCount: number;
  populatedAttributeCount: number;
};

export type AuditResult = {
  products: ProductAudit[];
  summary: {
    productsScanned: number;
    categorizedProducts: number;
    productsWithoutCategory: number;
    productsWithGaps: number;
    attributesChecked: number;
    missingAttributes: number;
    populatedAttributes: number;
  };
};

function categoryHandle(category: CategoryInput | null) {
  if (!category) return null;
  const part = category.id.split("/").filter(Boolean).pop();
  return part || null;
}

function hasValue(value: string | null | undefined) {
  return value != null && value.trim().length > 0 && value.trim() !== "[]";
}

export function auditCatalog(
  products: ProductInput[],
  definitions: DefinitionInput[],
): AuditResult {
  const audited = products.map<ProductAudit>((product) => {
    const handle = categoryHandle(product.category);
    if (!handle) {
      return {
        ...product,
        categoryHandle: null,
        attributes: [],
        status: "No category",
        missingAttributeCount: 0,
        populatedAttributeCount: 0,
      };
    }

    const applicable = definitions.filter((definition) =>
      definition.categoryValues.includes(handle),
    );
    const attributes = applicable.map<AttributeAudit>((definition) => {
      const field = product.metafields.find(
        (item) =>
          item.namespace === definition.namespace &&
          item.key === definition.key,
      );
      const value = field?.value ?? null;
      return {
        ...definition,
        value,
        status: hasValue(value) ? "Populated" : "Missing",
      };
    });
    const missingAttributeCount = attributes.filter(
      (item) => item.status === "Missing",
    ).length;
    const populatedAttributeCount =
      attributes.length - missingAttributeCount;

    return {
      ...product,
      categoryHandle: handle,
      attributes,
      status:
        attributes.length === 0
          ? "No applicable fields"
          : missingAttributeCount > 0
            ? "Incomplete"
            : "Complete",
      missingAttributeCount,
      populatedAttributeCount,
    };
  });

  const productsSorted = [...audited].sort((left, right) => {
    const rank = (item: ProductAudit) =>
      item.status === "Incomplete"
        ? 0
        : item.status === "No category"
          ? 1
          : item.status === "No applicable fields"
            ? 2
            : 3;
    return (
      rank(left) - rank(right) ||
      right.missingAttributeCount - left.missingAttributeCount ||
      left.title.localeCompare(right.title)
    );
  });
  const allAttributes = productsSorted.flatMap(
    (product) => product.attributes,
  );

  return {
    products: productsSorted,
    summary: {
      productsScanned: productsSorted.length,
      categorizedProducts: productsSorted.filter(
        (product) => product.category !== null,
      ).length,
      productsWithoutCategory: productsSorted.filter(
        (product) => product.category === null,
      ).length,
      productsWithGaps: productsSorted.filter(
        (product) => product.status === "Incomplete",
      ).length,
      attributesChecked: allAttributes.length,
      missingAttributes: allAttributes.filter(
        (item) => item.status === "Missing",
      ).length,
      populatedAttributes: allAttributes.filter(
        (item) => item.status === "Populated",
      ).length,
    },
  };
}

function csvCell(value: unknown) {
  let cell =
    value == null
      ? ""
      : String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(cell)) cell = "'" + cell;
  return '"' + cell.replaceAll('"', '""') + '"';
}

export function productAdminUrl(
  shopDomain: string,
  productId: string,
) {
  const safeDomain =
    /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/i.test(shopDomain)
      ? shopDomain.toLowerCase()
      : null;
  const safeProductId = /^\d+$/.test(productId)
    ? productId
    : null;
  return safeDomain && safeProductId
    ? "https://" + safeDomain + "/admin/products/" + safeProductId
    : "";
}

export function buildDiagnosticCsv(
  audit: AuditResult,
  shopDomain: string,
) {
  const rows: unknown[][] = [[
    "Product status",
    "Product",
    "Product admin link",
    "Shopify taxonomy category",
    "Category-specific field",
    "Namespace",
    "Key",
    "Observed value",
    "Coverage status",
  ]];

  for (const product of audit.products) {
    if (product.attributes.length === 0) {
      rows.push([
        product.status,
        product.title,
        productAdminUrl(
          shopDomain,
          product.legacyResourceId,
        ),
        product.category?.fullName || "",
        "",
        "",
        "",
        "",
        product.status,
      ]);
      continue;
    }

    for (const attribute of product.attributes) {
      rows.push([
        product.status,
        product.title,
        productAdminUrl(
          shopDomain,
          product.legacyResourceId,
        ),
        product.category?.fullName || "",
        attribute.name,
        attribute.namespace,
        attribute.key,
        attribute.value || "",
        attribute.status,
      ]);
    }
  }

  return rows
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n");
}
