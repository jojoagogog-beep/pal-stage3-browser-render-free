import { useLoaderData } from "react-router";
import { ImportIntegrityDashboard } from "./components/import-integrity-dashboard";
export default function App(){return <ImportIntegrityDashboard {...useLoaderData<any>()}/>;}
