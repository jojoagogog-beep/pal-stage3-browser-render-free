import SeoBulkDemo from "../special/seo-bulk-fixer/demo";
import VariantImageDemo from "../special/variant-image/demo";
import VariantOrderDemo from "../special/variant-order/demo";
import FeedReadinessDemo from "../special/feed-readiness/demo";
import ImportIntegrityDemo from "../special/import-row-integrity/demo";
import { useParams, useSearchParams } from "react-router";
import { MultiDashboard } from "../components/multi-dashboard";
import { demoProducts } from "../lib/demo-catalog";
import { ruleModules } from "../rules";
export default function ReviewDemo(){const {slug=""}=useParams();const [params]=useSearchParams();const definition=ruleModules[slug as keyof typeof ruleModules] as any;if(slug==="pal-seo-bulk-fixer")return <SeoBulkDemo/>;if(slug==="pal-variant-image-guard")return <VariantImageDemo/>;
if(slug==="pal-variant-order-guard")return <VariantOrderDemo/>;
if(slug==="pal-feed-readiness-guard")return <FeedReadinessDemo/>;
if(slug==="pal-import-row-integrity-guard")return <ImportIntegrityDemo/>;
if(!definition)return <main>Unknown app.</main>;
const state=params.get("state")||"all";
// The two product-type rules require the productType field. Unlike live
// Shopify catalog records, the common demo fixture did not include it,
// causing the public reviewer demo to throw a 500 before the UI rendered.
const typeRuleDemo=slug==="pal-type-empty-guard"||slug==="pal-type-length-guard";
const titleLengthDemo=slug==="pal-title-length-guard";
const demoCatalog=state==="empty"?[]:typeRuleDemo
  ? demoProducts.map((product,index)=>({
      ...product,
      productType:index===0?"":index===1
        ? "Apparel and Accessories with a Description Far Longer Than Fifty Characters"
        : "Accessories",
    }))
  : titleLengthDemo
  ? demoProducts.map((product,index)=>({
      ...product,
      title:index===0?"Cap":index===1
        ? "Women's Relaxed Fit Premium Organic Cotton Long Sleeve Outdoor Adventure Travel Layering Essential Top with Contrast Stitching"
        : product.title,
    }))
  : demoProducts;
return <MultiDashboard key={state} definition={definition} audit={definition.auditCatalog(demoCatalog as any)} demo initialFilter={state}/>}
