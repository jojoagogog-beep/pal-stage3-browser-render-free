import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Terms of Service · PAL Variant Order Guard" },
];

export default function Terms() {
  return (
    <PublicPage
      title="Terms of Service"
      intro="These terms apply to use of PAL Variant Order Guard as a read-only catalog structure audit inside Shopify."
    >
      <h2>Service</h2>
      <p>
        The app checks Shopify product option names, positions, and values for
        structural differences such as inconsistent option sequences, naming
        drift, duplicate option families, and numeric ordering that may need
        review.
      </p>

      <h2>Merchant responsibility</h2>
      <p>
        Findings are informational. Merchants decide whether an option order,
        label, or value sequence is intentional before making any change in
        Shopify.
      </p>

      <h2>No automatic correction</h2>
      <p>
        The first release is read-only. It does not change products, variants,
        themes, option labels, or option values and does not guarantee a
        particular storefront presentation.
      </p>

      <h2>Subscription</h2>
      <p>
        Paid plans, trials, renewals, and cancellations are administered through
        Shopify. The intended public plan is US$5.99 per month with a 7-day free
        trial; the price accepted through Shopify at subscription time controls.
      </p>

      <h2>Availability</h2>
      <p>
        The service may be changed, suspended, or discontinued subject to
        applicable obligations. Merchants must use the app lawfully.
      </p>

      <h2>Contact</h2>
      <p>Questions about these terms can be sent to practicalai_lab_jp@proton.me.</p>
    </PublicPage>
  );
}
