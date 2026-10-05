import { PublicPage } from "../components/public-page";

export const meta = () => [{ title: "Terms of Service · PAL Collection Ratio Guard" }];

export default function Terms() {
  return (
    <PublicPage
      title="Terms of Service"
      intro="These terms apply to PAL Collection Ratio Guard, a read-only collection image-ratio audit."
    >
      <h2>Service</h2>
      <p>The app reports observed collection image dimensions, practical aspect-ratio groups, and ratio outliers for merchant review.</p>
      <h2>Merchant responsibility</h2>
      <p>Findings are informational. Merchants decide what collection image ratio is appropriate for their storefront.</p>
      <h2>Read-only operation</h2>
      <p>The app does not upload, crop, replace, or edit collection images, products, themes, navigation, or customer data.</p>
      <h2>Coverage limits</h2>
      <p>Each synchronous run uses a collection safety limit and clearly reports when a result is partial.</p>
      <h2>Subscription</h2>
      <p>The intended public plan is US$4.99 per month with a 7-day free trial. Shopify administers billing, renewal, and cancellation.</p>
      <h2>Contact</h2>
      <p>Questions can be sent to practicalai_lab_jp@proton.me.</p>
    </PublicPage>
  );
}
