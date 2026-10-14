import test from "node:test";
import assert from "node:assert/strict";
import { auditCatalog as imageAudit } from "../app/special/variant-image/lib/variant-image-audit.ts";
import { auditCatalog as orderAudit } from "../app/special/variant-order/lib/variant-order-audit.ts";
import { auditCatalog as feedAudit } from "../app/special/feed-readiness/lib/feed-audit.ts";
import { auditCatalog as importAudit } from "../app/special/import-row-integrity/lib/import-integrity-audit.ts";

test("variant image detects mixed coverage and shared assignments", () => {
  const image={id:"img-1",alt:"Sample"};
  const result=imageAudit([{id:"p1",legacyResourceId:"1",title:"Demo",variants:[
    {id:"v1",legacyResourceId:"1",title:"Red",images:[image]},
    {id:"v2",legacyResourceId:"2",title:"Blue",images:[image]},
    {id:"v3",legacyResourceId:"3",title:"Green",images:[]}
  ]}]);
  assert.equal(result.summary.productsScanned,1);
  assert.equal(result.summary.variantsMissingImages,1);
  assert.deepEqual([...result.affectedProducts[0].issueKeys].sort(),["duplicate_image_assignment","missing_dedicated_image"].sort());
  assert.equal(imageAudit([]).summary.productsScanned,0);
});

test("variant order identifies inconsistent option sequences", () => {
  const p=(id,opts)=>({id,legacyResourceId:id,title:id,options:opts.map(([name,position])=>({name,position,values:["Red","Blue"]}))});
  const result=orderAudit([
    p("p1",[["Color",1],["Size",2]]),
    p("p2",[["Size",1],["Color",2]])
  ]);
  assert.ok(result.products.some(p=>p.issueKeys.includes("sequence_mismatch")));
  assert.equal(orderAudit([]).summary.productsScanned,0);
});

test("feed readiness identifies missing product image and category", () => {
  const result=feedAudit(
    [{id:"p1",legacyResourceId:"1",title:"Sample",vendor:"Brand",tags:[],categoryName:null,hasImage:false}],
    [{id:"v1",productId:"p1",title:"Default",sku:null,barcode:null}]
  );
  assert.equal(result.summary.productsWithActions,1);
  assert.ok(result.products[0].issueKeys.includes("missing_category"));
  assert.ok(result.products[0].issueKeys.includes("missing_image"));
  assert.equal(feedAudit([],[]).summary.productsScanned,0);
});

test("import integrity identifies duplicate SKU and mixed inventory tracking", () => {
  const product={id:"p1",legacyResourceId:"1",title:"Sample",handle:"sample"};
  const result=importAudit([
    {id:"v1",legacyResourceId:"1",title:"Red",sku:"SKU-1",barcode:null,inventoryTracked:true,product},
    {id:"v2",legacyResourceId:"2",title:"Blue",sku:"SKU-1",barcode:null,inventoryTracked:false,product}
  ]);
  assert.equal(result.summary.duplicateSkuGroups,1);
  for(const variant of result.variants){
    assert.ok(variant.issueKeys.includes("duplicate_sku"));
    assert.ok(variant.issueKeys.includes("mixed_inventory_tracking"));
  }
  assert.equal(importAudit([]).summary.variantsScanned,0);
});
