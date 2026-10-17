import assert from "node:assert/strict";
import * as sku from "../app/rules/pal-sku-format-consistency-guard.ts";
import * as collection from "../app/rules/pal-collection-coverage-guard.ts";
const p=[{id:"p1",title:"Sample",variants:{pageInfo:{hasNextPage:false},nodes:[{title:"One",sku:"AB-01"},{title:"Two",sku:"ab_02"}]}}];
assert.equal(sku.auditCatalog(p).findings.length,2);
assert.equal(sku.auditCatalog([{...p[0],variants:{pageInfo:{hasNextPage:true},nodes:p[0].variants.nodes}}]).findings.length,0);
assert.equal(collection.auditCatalog([{id:"p1",title:"Orphan",status:"ACTIVE",collections:{nodes:[]}},{id:"p2",title:"Covered",status:"ACTIVE",collections:{nodes:[{id:"c1"}]}}]).findings.length,1);
console.log("SKU_AND_COLLECTION_AUDIT_PASS");
