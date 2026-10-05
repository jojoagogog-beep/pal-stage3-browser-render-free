import type { CollectionInput } from "./collection-image-ratio-audit";

export const demoCollections: CollectionInput[] = [
  { id:"c1", legacyResourceId:"6101", title:"Summer Collection", handle:"summer", image:{ width:1600, height:1600 } },
  { id:"c2", legacyResourceId:"6102", title:"Travel Picks", handle:"travel", image:{ width:1200, height:1200 } },
  { id:"c3", legacyResourceId:"6103", title:"Wide Banners", handle:"wide-banners", image:{ width:1600, height:900 } },
  { id:"c4", legacyResourceId:"6104", title:"Portrait Edit", handle:"portrait-edit", image:{ width:900, height:1200 } },
  { id:"c5", legacyResourceId:"6105", title:"No Image Yet", handle:"no-image", image:null },
];

export function readyDemoCollections(): CollectionInput[] {
  return [
    { id:"r1", legacyResourceId:"6201", title:"New Arrivals", handle:"new-arrivals", image:{ width:1400, height:1400 } },
    { id:"r2", legacyResourceId:"6202", title:"Accessories", handle:"accessories", image:{ width:1200, height:1200 } },
    { id:"r3", legacyResourceId:"6203", title:"Seasonal", handle:"seasonal", image:{ width:1600, height:1600 } },
  ];
}
