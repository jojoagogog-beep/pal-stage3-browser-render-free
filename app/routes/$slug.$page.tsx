import VariantImagePrivacy from "../special/variant-image/privacy";
import VariantImageTerms from "../special/variant-image/terms";
import VariantImageSupport from "../special/variant-image/support";
import VariantOrderPrivacy from "../special/variant-order/privacy";
import VariantOrderTerms from "../special/variant-order/terms";
import VariantOrderSupport from "../special/variant-order/support";
import FeedReadinessPrivacy from "../special/feed-readiness/privacy";
import FeedReadinessTerms from "../special/feed-readiness/terms";
import FeedReadinessSupport from "../special/feed-readiness/support";
import ImportRowIntegrityPrivacy from "../special/import-row-integrity/privacy";
import ImportRowIntegrityTerms from "../special/import-row-integrity/terms";
import ImportRowIntegritySupport from "../special/import-row-integrity/support";
import { useParams } from "react-router";
import { ruleModules } from "../rules";
export default function PublicInfo(){
  const {slug="",page=""}=useParams();
  if(slug==="pal-variant-image-guard"&&page==="privacy")return <VariantImagePrivacy/>;
  if(slug==="pal-variant-image-guard"&&page==="terms")return <VariantImageTerms/>;
  if(slug==="pal-variant-image-guard"&&page==="support")return <VariantImageSupport/>;
  if(slug==="pal-variant-order-guard"&&page==="privacy")return <VariantOrderPrivacy/>;
  if(slug==="pal-variant-order-guard"&&page==="terms")return <VariantOrderTerms/>;
  if(slug==="pal-variant-order-guard"&&page==="support")return <VariantOrderSupport/>;
  if(slug==="pal-feed-readiness-guard"&&page==="privacy")return <FeedReadinessPrivacy/>;
  if(slug==="pal-feed-readiness-guard"&&page==="terms")return <FeedReadinessTerms/>;
  if(slug==="pal-feed-readiness-guard"&&page==="support")return <FeedReadinessSupport/>;
  if(slug==="pal-import-row-integrity-guard"&&page==="privacy")return <ImportRowIntegrityPrivacy/>;
  if(slug==="pal-import-row-integrity-guard"&&page==="terms")return <ImportRowIntegrityTerms/>;
  if(slug==="pal-import-row-integrity-guard"&&page==="support")return <ImportRowIntegritySupport/>;const d=ruleModules[slug as keyof typeof ruleModules] as any;
  if(!d||!["privacy","terms","support"].includes(page))return <main style={{fontFamily:"system-ui",padding:32}}><h1>Not found</h1></main>;
  const name="PAL "+String(d.appMeta?.shortName||"Catalog Guard");
  const body=page==="privacy"?"This app processes only the Shopify catalog data required to provide its read-only catalog review. It does not sell merchant data. Data is used only to operate, secure, and support the app."
    :page==="terms"?"Use of this app is subject to Shopify platform rules and these terms. Findings are review guidance. Merchants remain responsible for catalog changes and business decisions."
    :"Support: practicalai_lab_jp@proton.me";
  return <main style={{fontFamily:"system-ui",maxWidth:820,margin:"48px auto",padding:"0 24px"}}><p>Practical AI Lab</p><h1>{name} — {page[0].toUpperCase()+page.slice(1)}</h1><p>{body}</p><p>Last updated: October 6, 2026</p></main>;
}
