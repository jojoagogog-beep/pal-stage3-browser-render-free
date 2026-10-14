import type { VariantInput } from "./import-integrity-audit";

const product = (
  id: string,
  title: string,
  handle: string,
): VariantInput["product"] => ({
  id: `gid://shopify/Product/${id}`,
  legacyResourceId: id,
  title,
  handle,
});

const alpine = product("3001", "Alpine Shell Jacket", "alpine-shell-jacket");
const studio = product("3002", "Studio Cotton Tee", "studio-cotton-tee");
const ridge = product("3003", "Ridge Fleece", "ridge-fleece");
const field = product("3004", "Field Daypack", "field-daypack");
const defaultProduct = product("3005", "Default Title", "default-title");

export const demoVariants: VariantInput[] = [
  {
    id: "gid://shopify/ProductVariant/4001",
    legacyResourceId: "4001",
    title: "Black / Small",
    sku: "ALP-BLK-S",
    barcode: "880000000001",
    inventoryTracked: true,
    product: alpine,
  },
  {
    id: "gid://shopify/ProductVariant/4002",
    legacyResourceId: "4002",
    title: "Black / Medium",
    sku: "ALP-BLK-M",
    barcode: "880000000002",
    inventoryTracked: false,
    product: alpine,
  },
  {
    id: "gid://shopify/ProductVariant/4003",
    legacyResourceId: "4003",
    title: "White / Small",
    sku: "TEE-WHT-S",
    barcode: null,
    inventoryTracked: true,
    product: studio,
  },
  {
    id: "gid://shopify/ProductVariant/4004",
    legacyResourceId: "4004",
    title: "White / Medium",
    sku: " tee-wht-s ",
    barcode: "880000000004",
    inventoryTracked: true,
    product: studio,
  },
  {
    id: "gid://shopify/ProductVariant/4005",
    legacyResourceId: "4005",
    title: "Navy / Small",
    sku: null,
    barcode: "880000000005",
    inventoryTracked: true,
    product: ridge,
  },
  {
    id: "gid://shopify/ProductVariant/4006",
    legacyResourceId: "4006",
    title: "Olive",
    sku: null,
    barcode: null,
    inventoryTracked: true,
    product: field,
  },
  {
    id: "gid://shopify/ProductVariant/4007",
    legacyResourceId: "4007",
    title: "Default Title",
    sku: null,
    barcode: null,
    inventoryTracked: false,
    product: defaultProduct,
  },
];

export function readyDemoCatalog(): VariantInput[] {
  const readyAlpine = product(
    "5001",
    "Alpine Shell Jacket",
    "alpine-shell-jacket",
  );
  const readyTote = product(
    "5002",
    "Everyday Canvas Tote",
    "everyday-canvas-tote",
  );
  return [
    {
      id: "gid://shopify/ProductVariant/6001",
      legacyResourceId: "6001",
      title: "Black / Small",
      sku: "ALP-BLK-S",
      barcode: "880000000101",
      inventoryTracked: true,
      product: readyAlpine,
    },
    {
      id: "gid://shopify/ProductVariant/6002",
      legacyResourceId: "6002",
      title: "Black / Medium",
      sku: "ALP-BLK-M",
      barcode: "880000000102",
      inventoryTracked: true,
      product: readyAlpine,
    },
    {
      id: "gid://shopify/ProductVariant/6003",
      legacyResourceId: "6003",
      title: "Natural",
      sku: "TOTE-NAT",
      barcode: "880000000103",
      inventoryTracked: false,
      product: readyTote,
    },
  ];
}

export function demoCatalogFor(state: string): VariantInput[] {
  if (state === "ready") return readyDemoCatalog();
  if (state === "duplicates") {
    return demoVariants.filter((variant) => variant.product.id === studio.id);
  }
  if (state === "identifiers") {
    return demoVariants.filter((variant) =>
      [ridge.id, field.id, defaultProduct.id].includes(variant.product.id),
    );
  }
  if (state === "tracking") {
    return demoVariants.filter((variant) => variant.product.id === alpine.id);
  }
  return demoVariants;
}
