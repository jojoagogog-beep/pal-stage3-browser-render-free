import VariantImageDemo from "../special/variant-image/demo";
import VariantOrderDemo from "../special/variant-order/demo";
import FeedReadinessDemo from "../special/feed-readiness/demo";
import ImportIntegrityDemo from "../special/import-row-integrity/demo";
import { useParams, useSearchParams } from "react-router";
import { MultiDashboard } from "../components/multi-dashboard";
import { demoProducts } from "../lib/demo-catalog";
import { ruleModules } from "../rules";
export default function ReviewDemo(){const {slug=""}=useParams();const [params]=useSearchParams();const definition=ruleModules[slug as keyof typeof ruleModules] as any;if(slug==="pal-variant-image-guard")return <VariantImageDemo/>;
if(slug==="pal-variant-order-guard")return <VariantOrderDemo/>;
if(slug==="pal-feed-readiness-guard")return <FeedReadinessDemo/>;
if(slug==="pal-import-row-integrity-guard")return <ImportIntegrityDemo/>;
if(!definition)return <main>Unknown app.</main>;const state=params.get("state")||"all";return <MultiDashboard key={state} definition={definition} audit={definition.auditCatalog(state==="empty"?[]:demoProducts as any)} demo initialFilter={state}/>}
