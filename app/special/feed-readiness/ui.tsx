import { useLoaderData } from "react-router";
import { FeedDashboard } from "./components/feed-dashboard";
export default function App(){return <FeedDashboard {...useLoaderData<any>()}/>;}
