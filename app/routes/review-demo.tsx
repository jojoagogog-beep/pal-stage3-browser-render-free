import { useSearchParams } from 'react-router';
import { DescriptionDashboard } from '../components/description-dashboard';
import { auditCatalog } from '../lib/description-audit';
import { demoProducts } from '../lib/demo-catalog';
export default function ReviewDemo(){const [params]=useSearchParams();const state=params.get('state')||'all';return <DescriptionDashboard key={state} audit={auditCatalog(state==='empty'?[]:state==='clean'?[demoProducts[2]]:demoProducts)} demo initialFilter={state}/>;}
