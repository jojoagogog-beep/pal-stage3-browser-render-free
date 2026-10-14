import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Terms of Service · PAL Feed Readiness Guard" },
];

export default function Terms() {
  return (
    <PublicPage
      title="Terms of Service"
      intro="These terms apply to use of PAL Feed Readiness Guard as a catalog pre-flight aid inside Shopify admin."
    >
      <h2>Service</h2>
      <p>
        The app checks selected Shopify product and variant fields for common
        catalog-readiness gaps and can export a remediation CSV. The first
        release is read-only and does not automatically edit product data.
      </p>

      <h2>Merchant responsibility</h2>
      <p>
        Merchants are responsible for the accuracy of product data, for deciding
        whether identifier rules apply to custom or print-on-demand products,
        and for reviewing changes before making them in Shopify or a sales
        channel.
      </p>

      <h2>No approval guarantee</h2>
      <p>
        The audit is informational. Google, Meta, Shopify, and other channels
        apply their own policies and may use information that the app does not
        inspect. A clear audit does not guarantee listing acceptance,
        visibility, or advertising performance.
      </p>

      <h2>Subscription</h2>
      <p>
        Paid plans, trials, renewals, and cancellations are administered through
        Shopify. The current intended public plan is US$6.99 per month with a
        7-day free trial; the price displayed and accepted through Shopify at
        subscription time controls.
      </p>

      <h2>Acceptable use and availability</h2>
      <p>
        Merchants must use the app lawfully and may not attempt to interfere
        with its security or service. The service may be changed, suspended, or
        discontinued, subject to applicable obligations.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms can be sent to practicalai_lab_jp@proton.me.
      </p>
    </PublicPage>
  );
}
