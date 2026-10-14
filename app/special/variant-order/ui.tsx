import { useLoaderData } from "react-router";
import { VariantDashboard } from "./components/variant-dashboard";
export default function App(){return <VariantDashboard {...useLoaderData<any>()}/>;}
