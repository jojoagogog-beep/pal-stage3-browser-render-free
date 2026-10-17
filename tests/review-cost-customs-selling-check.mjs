import assert from "node:assert/strict";
import * as costs from "../app/rules/pal-unit-cost-coverage-guard.ts";
import * as customs from "../app/rules/pal-customs-data-readiness-guard.ts";
import * as plans from "../app/rules/pal-selling-plan-coverage-guard.ts";
const row={id:"p",title:"Sample",variants:{pageInfo:{hasNextPage:false},nodes:[
 {id:"a",title:"A",sku:"A",inventoryItem:{unitCost:null,requiresShipping:true,harmonizedSystemCode:null,countryCodeOfOrigin:null},sellingPlanGroups:{pageInfo:{hasNextPage:false},nodes:[{id:"s1"}]}},
 {id:"b",title:"B",sku:"B",inventoryItem:{unitCost:{amount:"1",currencyCode:"USD"},requiresShipping:false,harmonizedSystemCode:null,countryCodeOfOrigin:null},sellingPlanGroups:{pageInfo:{hasNextPage:false},nodes:[]}}
]}};
assert.equal(costs.auditCatalog([row]).findings.length,1);
assert.equal(customs.auditCatalog([row]).findings.length,1);
assert.equal(plans.auditCatalog([row]).findings.length,2);
console.log("COST_CUSTOMS_AND_SELLING_TESTS_PASS");
