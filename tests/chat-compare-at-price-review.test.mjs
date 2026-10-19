import assert from "node:assert/strict";
import {auditCatalog,buildCsv} from "../app/rules/pal-compare-at-price-guard.ts";
const p=(id,vs,more=false)=>({id:"gid://shopify/Product/"+id,title:"Product "+id,
 variants:{pageInfo:{hasNextPage:more},nodes:vs.map((v,i)=>({id:"v"+i,title:"Variant "+i,price:v[0],compareAtPrice:v[1]}))}});
const a=auditCatalog([p(1,[["10.00","12.00"],["10.00","10.00"],["10.00","9.50"]]),p(2,[["1.00",null]]),p(3,[["4","3"]],true)]);
assert.equal(a.products,3);
assert.equal(a.findings.length,2);
assert.equal(a.skipped.length,1);
assert(a.findings.every(x=>x.rule==="invalid_compare_at"));
assert(buildCsv(a.findings).includes("Compare-at price"));
console.log("PASS compare-at pricing invalid/equal/missing/incomplete and CSV");
