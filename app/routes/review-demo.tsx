import {useSearchParams} from "react-router";
import {ProductAuditDashboard} from "../components/product-audit-dashboard";
import {auditProducts} from "../lib/product-audit";
import {demoProducts,readyProducts} from "../lib/demo-catalog";
const APP_NAME="PAL Product Image Alt Guard", MODE="image_alt";
export default function ReviewDemo(){const[p]=useSearchParams();const s=p.get("state")||"overview";const products=s==="ready"?readyProducts:s==="issue"?demoProducts.slice(0,2):demoProducts;return <ProductAuditDashboard appName={APP_NAME} mode={MODE} audit={auditProducts(products,MODE)} shopDomain="sample-shop.myshopify.com" shopName="PAL Sample Catalog" scannedAt="Oct 2, 2026, 4:50 PM UTC" coverageLimited={s==="limit"} showExport={false} demo/>;}
