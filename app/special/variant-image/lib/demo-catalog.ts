import type { ProductInput } from "./variant-image-audit";

const image = (id: string, alt: string) => ({
  id: `gid://shopify/MediaImage/${id}`,
  alt,
});

export const demoProducts: ProductInput[] = [
  {
    id: "gid://shopify/Product/3001",
    legacyResourceId: "3001",
    title: "Sample Coastal Linen Shirt",
    variants: [
      {
        id: "gid://shopify/ProductVariant/4001",
        legacyResourceId: "4001",
        title: "Navy / Small",
        images: [image("7001", "Navy linen shirt")],
      },
      {
        id: "gid://shopify/ProductVariant/4002",
        legacyResourceId: "4002",
        title: "Navy / Medium",
        images: [],
      },
      {
        id: "gid://shopify/ProductVariant/4003",
        legacyResourceId: "4003",
        title: "Sand / Small",
        images: [image("7002", "Sand linen shirt")],
      },
      {
        id: "gid://shopify/ProductVariant/4004",
        legacyResourceId: "4004",
        title: "Sand / Medium",
        images: [],
      },
    ],
  },
  {
    id: "gid://shopify/Product/3002",
    legacyResourceId: "3002",
    title: "Sample Trail Daypack",
    variants: [
      {
        id: "gid://shopify/ProductVariant/4011",
        legacyResourceId: "4011",
        title: "Pine",
        images: [image("7010", "Pine daypack")],
      },
      {
        id: "gid://shopify/ProductVariant/4012",
        legacyResourceId: "4012",
        title: "Moss",
        images: [image("7010", "Pine daypack")],
      },
      {
        id: "gid://shopify/ProductVariant/4013",
        legacyResourceId: "4013",
        title: "Clay",
        images: [image("7011", "Clay daypack")],
      },
    ],
  },
  {
    id: "gid://shopify/Product/3003",
    legacyResourceId: "3003",
    title: "Sample Merino Scarf",
    variants: [
      {
        id: "gid://shopify/ProductVariant/4021",
        legacyResourceId: "4021",
        title: "Oat",
        images: [image("7021", "Oat merino scarf")],
      },
      {
        id: "gid://shopify/ProductVariant/4022",
        legacyResourceId: "4022",
        title: "Charcoal",
        images: [image("7022", "Charcoal merino scarf")],
      },
    ],
  },
  {
    id: "gid://shopify/Product/3004",
    legacyResourceId: "3004",
    title: "Sample Digital Gift Card",
    variants: [
      {
        id: "gid://shopify/ProductVariant/4031",
        legacyResourceId: "4031",
        title: "$25",
        images: [],
      },
      {
        id: "gid://shopify/ProductVariant/4032",
        legacyResourceId: "4032",
        title: "$50",
        images: [],
      },
    ],
  },
];

export function demoCatalogFor(state: string): ProductInput[] {
  if (state === "mixed") return demoProducts.slice(0, 1);
  if (state === "duplicates") return demoProducts.slice(1, 2);
  if (state === "clear") return demoProducts.slice(2);
  return demoProducts;
}
