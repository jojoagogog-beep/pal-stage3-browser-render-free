// Static GraphQL query regression tests; no Shopify shop credentials or network.
import fs from "node:fs";
import assert from "node:assert/strict";
import {parse,visit,Kind} from "graphql";

const apps=["variant-image","variant-order","feed-readiness","import-row-integrity"];
let checked=0;
for (const slug of apps) {
  const source=fs.readFileSync("app/special/"+slug+"/route.server.tsx","utf8");
  const matches=[...source.matchAll(/const\s+(\w+_QUERY)\s*=\s*`([\s\S]*?)`;/g)];
  assert.ok(matches.length>0,"No Shopify Admin GraphQL queries found in "+slug);
  for(const [,variable,query] of matches) {
    const ast=parse(query);
    assert.equal(ast.definitions.length,1,slug+" "+variable);
    const operation=ast.definitions[0];
    assert.equal(operation.operation,"query",slug+" "+variable+" should remain read-only");
    const declared=new Set(operation.variableDefinitions?.map(v=>v.variable.name.value)||[]);
    assert.ok(declared.has("first")&&declared.has("cursor"),
      slug+" "+variable+" must paginate safely");
    let connection=false,pageInfo=false,unsafeMutation=false;
    visit(ast,{
      Field(node) {
        if(["products","productVariants"].includes(node.name.value)) {
          connection=true;
          const vars=new Map((node.arguments||[]).map(a=>[a.name.value,a.value]));
          assert.equal(vars.get("first")?.name?.value,"first",
            slug+" "+variable+" must cap each query page");
          assert.equal(vars.get("after")?.name?.value,"cursor",
            slug+" "+variable+" must include a stable cursor");
        }
        if(node.name.value==="pageInfo")pageInfo=true;
        if(node.name.value==="mutation")unsafeMutation=true;
      }
    });
    assert.ok(connection&&pageInfo&&!unsafeMutation,
      slug+" "+variable+" requires catalog pagination");
    console.log("PASS",slug,variable,"AST + read-only pagination");
    checked++;
  }
}
assert.equal(checked,5);
console.log("ALL FIVE SHOPIFY GRAPHQL STATIC CHECKS PASSED");
