import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Terms of Service · PAL Variant Image Guard" },
];

export default function Terms() {
  return (
    <PublicPage
      title="Terms of Service"
      intro="These terms apply to use of PAL Variant Image Guard as a read-only product media assignment audit for Shopify."
    >
      <h2>Service</h2>
      <p>
        The app checks Shopify variant media assignments for mixed image
        coverage and images assigned to multiple variants of the same product.
        It groups affected products and can export a review CSV.
      </p>

      <h2>Merchant responsibility</h2>
      <p>
        Findings are informational. An absent or shared variant image can be
        intentional. Merchants decide whether each assignment needs a change in
        Shopify.
      </p>

      <h2>No automatic correction</h2>
      <p>
        The first release is read-only. It does not change products, variants,
        media, themes, or storefront behavior and does not guarantee a
        particular storefront presentation.
      </p>

      <h2>Subscription</h2>
      <p>
        Paid plans, trials, renewals, and cancellations are administered through
        Shopify App Pricing. The intended public plan is US$5.99 per month with
        a 7-day free trial; the terms accepted through Shopify at subscription
        time control.
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
