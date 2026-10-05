import { useParams, useSearchParams } from "react-router";
import { MultiDashboard } from "../components/multi-dashboard";
import { demoProducts } from "../lib/demo-catalog";
import { ruleModules } from "../rules";
export default function ReviewDemo(){const {slug=""}=useParams();const [params]=useSearchParams();const definition=ruleModules[slug as keyof typeof ruleModules] as any;if(!definition)return <main>Unknown app.</main>;const state=params.get("state")||"all";return <MultiDashboard key={state} definition={definition} audit={definition.auditCatalog(state==="empty"?[]:demoProducts as any)} demo initialFilter={state}/>}
