import type { ProductInput } from "./variant-order-audit";

export const demoProducts: ProductInput[] = [
  {
    id: "gid://shopify/Product/1001",
    legacyResourceId: "1001",
    title: "Alpine Shell Jacket",
    options: [
      { name: "Size", position: 1, values: ["XS", "S", "M", "L"] },
      { name: "Color", position: 2, values: ["Black", "Moss", "Stone"] },
    ],
  },
  {
    id: "gid://shopify/Product/1002",
    legacyResourceId: "1002",
    title: "Ridge Fleece Jacket",
    options: [
      { name: "Color", position: 1, values: ["Navy", "Rust"] },
      { name: "Size", position: 2, values: ["S", "M", "L", "XL"] },
    ],
  },
  {
    id: "gid://shopify/Product/1003",
    legacyResourceId: "1003",
    title: "Studio Cotton Tee",
    options: [
      { name: "Size", position: 1, values: ["S", "M", "L"] },
      { name: "Colour", position: 2, values: ["White", "Charcoal"] },
    ],
  },
  {
    id: "gid://shopify/Product/1004",
    legacyResourceId: "1004",
    title: "Workshop Storage Canister",
    options: [
      { name: "Size", position: 1, values: ["5.0 L", "12.5 L", "1.0 L"] },
    ],
  },
  {
    id: "gid://shopify/Product/1005",
    legacyResourceId: "1005",
    title: "Woven Hall Rug",
    options: [
      { name: "Width", position: 1, values: ["60 cm", "80 cm"] },
      { name: "Length", position: 2, values: ["120 cm", "180 cm"] },
    ],
  },
  {
    id: "gid://shopify/Product/1006",
    legacyResourceId: "1006",
    title: "Woven Runner Rug",
    options: [
      { name: "Width", position: 1, values: ["60 cm", "80 cm"] },
      { name: "Length", position: 2, values: ["180 cm", "240 cm"] },
    ],
  },
];

export function readyDemoCatalog(): ProductInput[] {
  return [
    {
      id: "gid://shopify/Product/2001",
      legacyResourceId: "2001",
      title: "Alpine Shell Jacket",
      options: [
        { name: "Size", position: 1, values: ["XS", "S", "M", "L"] },
        { name: "Color", position: 2, values: ["Black", "Moss", "Stone"] },
      ],
    },
    {
      id: "gid://shopify/Product/2002",
      legacyResourceId: "2002",
      title: "Ridge Fleece Jacket",
      options: [
        { name: "Size", position: 1, values: ["S", "M", "L", "XL"] },
        { name: "Color", position: 2, values: ["Navy", "Rust"] },
      ],
    },
    {
      id: "gid://shopify/Product/2003",
      legacyResourceId: "2003",
      title: "Workshop Storage Canister",
      options: [
        { name: "Size", position: 1, values: ["1.0 L", "5.0 L", "12.5 L"] },
      ],
    },
  ];
}
