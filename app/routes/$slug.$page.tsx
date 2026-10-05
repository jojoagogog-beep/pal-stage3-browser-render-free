import { useParams } from "react-router";
import { ruleModules } from "../rules";
export default function PublicInfo(){
  const {slug="",page=""}=useParams();const d=ruleModules[slug as keyof typeof ruleModules] as any;
  if(!d||!["privacy","terms","support"].includes(page))return <main style={{fontFamily:"system-ui",padding:32}}><h1>Not found</h1></main>;
  const name="PAL "+String(d.appMeta?.shortName||"Catalog Guard");
  const body=page==="privacy"?"This app processes only the Shopify catalog data required to provide its read-only catalog review. It does not sell merchant data. Data is used only to operate, secure, and support the app."
    :page==="terms"?"Use of this app is subject to Shopify platform rules and these terms. Findings are review guidance. Merchants remain responsible for catalog changes and business decisions."
    :"Support: practicalai_lab_jp@proton.me";
  return <main style={{fontFamily:"system-ui",maxWidth:820,margin:"48px auto",padding:"0 24px"}}><p>Practical AI Lab</p><h1>{name} — {page[0].toUpperCase()+page.slice(1)}</h1><p>{body}</p><p>Last updated: October 6, 2026</p></main>;
}
