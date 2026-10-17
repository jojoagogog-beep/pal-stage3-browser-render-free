import assert from "node:assert/strict";
import {auditCatalog} from "../app/rules/pal-variant-shipping-policy-guard.ts";
const product={id:"p1",title:"Test",variants:{pageInfo:{hasNextPage:false},nodes:[
{id:"v1",title:"Physical",inventoryItem:{requiresShipping:true,tracked:true,measurement:{weight:{value:0,unit:"GRAMS"}}}},
{id:"v2",title:"Digital",inventoryItem:{requiresShipping:false,tracked:false,measurement:{weight:null}}}
]}};
const result=auditCatalog([product]);assert.ok(result.findings.some(x=>x.rule==="weight"));assert.ok(result.findings.some(x=>x.rule==="shipping"));assert.ok(result.findings.some(x=>x.rule==="tracking"));assert.equal(auditCatalog([{...product,variants:{...product.variants,pageInfo:{hasNextPage:true}}}]).findings.length,0);
console.log("VARIANT_SHIPPING_TEST_PASSED");
