# PAL Category Attribute Guard — App Store self-review

Review date: 2026-10-02

The canonical self-review requirements were fetched from Shopify with `shopify doc fetch` from the app root before this local code review. This report does not represent an official Shopify review.

## Summary

✅ **Likely passing:** 27  
❌ **Likely failing:** 1  
⚠️ **Needs review:** 3  
⏭️ **Groups skipped:** 10 _(see below)_

**Note:** The agent has reviewed a subset of requirements that have been selected by Shopify as checkable against a local codebase without browser context. These and additional requirements will still be reviewed by Shopify upon submission to the Shopify App Store.

## ⚠️ Requirements that need review

⚠️ **1.2.1 Use Shopify App Pricing or the Shopify Billing API**

**Why this needs attention:** The app is intended to charge US$5.99/month with a 7-day trial, but Managed Pricing is configured outside this repository and was not inspected. Confirm that the public app uses Shopify App Pricing before submission. If it does not, Shopify Billing must be implemented; off-platform billing is not permitted.

**What was detected:** `docs/product-spec.json`, `docs/app-store-submission.md`, and `app/routes/terms.tsx` describe the paid plan. The submission checklist still says to configure Shopify App Pricing. No Billing API mutation or third-party merchant-billing integration was found locally.

⚠️ **1.2.2 Implement Shopify App Pricing or the Shopify Billing API correctly**

**Why this needs attention:** Correct approval, decline, reinstall, and resubscription behavior cannot be established from the local code because the intended Managed Pricing configuration is external. Exercise those paths on the review app before submission.

**What was detected:** `app/routes/welcome.tsx` authenticates the merchant, accepts Shopify's `plan_handle`, and redirects to `/app`, but the repository contains no local evidence of the configured plan or completed approval, decline, and reinstall tests.

⚠️ **3.1.1 Use a valid TLS/SSL certificate**

**Why this needs attention:** A currently valid production certificate and HTTPS-only production behavior cannot be confirmed from local files. Replace or confirm the temporary tunnel configuration with the final public HTTPS origin and verify its certificate before submission.

**What was detected:** `shopify.app.toml`, `shopify.app.linked.toml`, and generated Shopify bundle manifests use HTTPS `trycloudflare.com` tunnel URLs. No stable production hostname or production TLS configuration is present in the repository.

## ❌ Requirements that are likely failing

❌ **1.1.4 Use only factual information**

**Why this matters:** Public app, legal, support, and reviewer surfaces must describe the submitted app accurately. Shipping the checked-in gateway would present a different product and unsupported fixed metrics.

**What was found:** `gateway/wrangler.jsonc` defines a worker named `pal-seo-bulk-fixer` with a `PAL_SEO_VPC` binding. `gateway/src/index.js` serves privacy, terms, support, and `/review-app` content for “PAL SEO Bulk Fixer,” not PAL Category Attribute Guard, and displays fixed figures such as “SEO score 72/100,” “Products with issues 14,” and “Missing alt text 27.” This deployable local component must not be used for this app in its present form.

## Skipped groups

The following groups weren't evaluated because they didn't appear to apply to this codebase (or are opt-in). If you'd like me to check any of these anyway, just ask.

- **5.1 Online store** — No `shopify.extension.toml` with `type = "theme"` was detected.
- **5.2 Payment** — No payment extension or `write_payment_gateway` scope was detected.
- **5.3 Payment facilitator** — Opt-in only; not requested.
- **5.4 Purchase option** — No customer payment method, own subscription contract, or payment mandate scopes were detected.
- **5.5 Product sourcing** — Opt-in only; not requested.
- **5.6 Checkout customization** — No checkout UI extension target was detected.
- **5.7 Sales channel** — No `channel_config` extension was detected.
- **5.8 Post purchase** — No `checkout_post_purchase` extension was detected.
- **5.9 Mobile app builders** — Opt-in only; not requested.
- **5.10 Donation** — Opt-in only; not requested.

## Resources

- [App Store requirements documentation](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements)
- [Best practices for apps](https://shopify.dev/docs/apps/launch/shopify-app-store/best-practices)
- [About billing for your app](https://shopify.dev/docs/apps/launch/billing)
- [Submitting your app for review](https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review)
