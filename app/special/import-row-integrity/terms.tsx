import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Terms of Service · PAL Import Row Integrity Guard" },
];

export default function Terms() {
  return (
    <PublicPage
      title="Terms of Service"
      intro="These terms apply to use of PAL Import Row Integrity Guard as a read-only catalog audit for Shopify."
    >
      <h2>Service</h2>
      <p>
        The app checks live Shopify catalog records for repeated SKUs, missing
        variant identifiers, suspicious Default Title rows, and mixed inventory
        tracking settings that may need review.
      </p>

      <h2>Merchant responsibility</h2>
      <p>
        Findings are informational. Merchants decide whether each SKU,
        identifier, title, or tracking pattern is intentional before making any
        change in Shopify or in a future import file.
      </p>

      <h2>No automatic correction</h2>
      <p>
        The first release is read-only. It does not change products, variants,
        inventory, themes, or CSV files and does not guarantee that a source
        file is valid or that every catalog issue will be detected.
      </p>

      <h2>Subscription</h2>
      <p>
        Paid plans, trials, renewals, and cancellations are administered through
        Shopify. The intended public plan is US$6.99 per month with a 7-day free
        trial; the price accepted through Shopify at subscription time controls.
      </p>

      <h2>Availability</h2>
      <p>
        The service may be changed, suspended, or discontinued subject to
        applicable obligations. Merchants must use the app lawfully.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms can be sent to practicalai_lab_jp@proton.me.
      </p>
    </PublicPage>
  );
}
