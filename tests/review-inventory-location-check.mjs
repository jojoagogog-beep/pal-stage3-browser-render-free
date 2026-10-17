import assert from "node:assert/strict";
import {auditCatalog} from "../app/rules/pal-inventory-location-consistency-guard.ts";
const p={id:"p",title:"Widget",variants:{pageInfo:{hasNextPage:false},nodes:[
{id:"a",title:"One",inventoryItem:{tracked:true,inventoryLevels:{pageInfo:{hasNextPage:false},nodes:[{location:{id:"locA"}}]}}},
{id:"b",title:"Two",inventoryItem:{tracked:true,inventoryLevels:{pageInfo:{hasNextPage:false},nodes:[{location:{id:"locB"}}]}}}
]}};
assert.equal(auditCatalog([p]).findings.length,2);
assert.equal(auditCatalog([{...p,variants:{...p.variants,pageInfo:{hasNextPage:true}}}]).findings.length,0);
console.log("INVENTORY_LOCATION_AUDIT_PASS");
