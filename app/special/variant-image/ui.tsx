import { useLoaderData } from "react-router";
import { VariantImageDashboard } from "./components/variant-image-dashboard";
export default function App(){return <VariantImageDashboard {...useLoaderData<any>()}/>;}
