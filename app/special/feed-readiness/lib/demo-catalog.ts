import type { ProductInput, VariantInput } from "./feed-audit";

export const demoProducts: ProductInput[] = [
  {
    id: "gid://shopify/Product/1001",
    legacyResourceId: "1001",
    title: "Trail Daypack",
    vendor: "Northline Goods",
    tags: ["outdoor"],
    categoryName: "Luggage & Bags > Backpacks",
    hasImage: true,
  },
  {
    id: "gid://shopify/Product/1002",
    legacyResourceId: "1002",
    title: "Personalized Ceramic Mug",
    vendor: "",
    tags: ["personalized", "print on demand"],
    categoryName: "Home & Garden > Kitchen & Dining > Drinkware > Mugs",
    hasImage: true,
  },
  {
    id: "gid://shopify/Product/1003",
    legacyResourceId: "1003",
    title: "Linen Market Tote",
    vendor: "PAL Demo Textiles",
    tags: ["accessories"],
    categoryName: null,
    hasImage: true,
  },
  {
    id: "gid://shopify/Product/1004",
    legacyResourceId: "1004",
    title: "Minimal Desk Lamp",
    vendor: "Atelier North",
    tags: ["lighting"],
    categoryName: "Home & Garden > Lighting > Lamps",
    hasImage: false,
  },
  {
    id: "gid://shopify/Product/1005",
    legacyResourceId: "1005",
    title: "Handmade Wool Cushion",
    vendor: "Studio Loom",
    tags: ["handmade", "made-to-order"],
    categoryName: "Home & Garden > Decor > Throw Pillows",
    hasImage: true,
  },
  {
    id: "gid://shopify/Product/1006",
    legacyResourceId: "1006",
    title: "Everyday Water Bottle",
    vendor: "Clear Peak",
    tags: ["drinkware"],
    categoryName:
      "Home & Garden > Kitchen & Dining > Drinkware > Water Bottles",
    hasImage: true,
  },
];

export const demoVariants: VariantInput[] = [
  {
    id: "v-1",
    productId: demoProducts[0].id,
    title: "Forest",
    sku: "NLG-DAY-FOR",
    barcode: "008500001001",
  },
  {
    id: "v-2",
    productId: demoProducts[0].id,
    title: "Clay",
    sku: "NLG-DAY-CLY",
    barcode: null,
  },
  {
    id: "v-3",
    productId: demoProducts[1].id,
    title: "11 oz",
    sku: "MUG-11-WHT",
    barcode: null,
  },
  {
    id: "v-4",
    productId: demoProducts[2].id,
    title: "Natural",
    sku: null,
    barcode: "008500001004",
  },
  {
    id: "v-5",
    productId: demoProducts[3].id,
    title: "Black",
    sku: "AN-LAMP-BLK",
    barcode: "008500001005",
  },
  {
    id: "v-6",
    productId: demoProducts[4].id,
    title: "Sage",
    sku: "SL-CUSH-SAG",
    barcode: null,
  },
  {
    id: "v-7",
    productId: demoProducts[5].id,
    title: "20 oz",
    sku: "CP-BTL-20",
    barcode: "008500001007",
  },
];

export function readyDemoCatalog() {
  return {
    products: demoProducts.map((product) => ({
      ...product,
      vendor: product.vendor || "PAL Demo Studio",
      categoryName: product.categoryName || "Apparel & Accessories > Handbags",
      hasImage: true,
      tags: product.tags.filter(
        (tag) =>
          ![
            "personalized",
            "print on demand",
            "handmade",
            "made-to-order",
          ].includes(tag),
      ),
    })),
    variants: demoVariants.map((variant, index) => ({
      ...variant,
      sku: variant.sku || `DEMO-SKU-${index + 1}`,
      barcode: variant.barcode || `00850000900${index + 1}`,
    })),
  };
}
