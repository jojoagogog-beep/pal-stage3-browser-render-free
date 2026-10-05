import type { CollectionInput } from "./collection-sort-audit";

export const demoCollections: CollectionInput[] = [
  {
    id: "s1", legacyResourceId: "5001",
    title: "Featured Products", handle: "featured-products",
    sortOrder: "MANUAL",
  },
  {
    id: "s2", legacyResourceId: "5002",
    title: "Best Sellers", handle: "best-sellers",
    sortOrder: "BEST_SELLING",
  },
  {
    id: "s3", legacyResourceId: "5003",
    title: "New Arrivals", handle: "new-arrivals",
    sortOrder: "CREATED_AT_DESC",
  },
  {
    id: "s4", legacyResourceId: "5004",
    title: "Price: Low to High", handle: "price-low-high",
    sortOrder: "PRICE_ASC",
  },
];

export function automaticDemoCollections(): CollectionInput[] {
  return demoCollections.filter((collection) => collection.sortOrder !== "MANUAL");
}
