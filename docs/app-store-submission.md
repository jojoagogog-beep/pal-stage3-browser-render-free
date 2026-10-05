# PAL Collection Sort Guard — App Store submission draft

## Listing identity
- App name: PAL Collection Sort Guard
- Primary language: English
- Distribution: public Shopify App Store app
- Admin experience: non-embedded
- Intended price: US$4.99/month
- Trial: 7 days
- Minimum scope: `read_products`
- Protected customer data: not used

## App introduction
Audit collection sort modes before making merchandising changes.

## App details
PAL Collection Sort Guard provides a read-only inventory of Shopify collection sort orders. It highlights collections using manual sort order, summarizes automatic sort modes used across the catalog, links to the matching Shopify Admin collection, and exports a diagnostic CSV.

The app never changes collection order or writes collection data.

## Feature bullets
1. Show each collection's current sort order.
2. Highlight collections using manual sort.
3. Summarize sort-mode usage across the catalog.

## Scope justification
`read_products` is used to read collections and their current sort order. No write, customer, order, theme, or navigation scope is requested.

## Reviewer test steps
1. Install the app and approve only `read_products`.
2. Create or use collections with different sort orders.
3. Include at least one collection using manual sort order.
4. Run the audit.
5. Confirm each collection's observed sort order is reported accurately.
6. Confirm manual-sort collections are separated from automatically sorted collections.
7. Open a collection link and confirm it resolves to the matching Shopify Admin collection.
8. Export the CSV and confirm collection, sort order, manual-sort flag, and Admin link are included.
9. Run the audit again and confirm no collection order is changed.
10. Visit `/privacy`, `/terms`, and `/support`.

## Public reviewer demo
- `/review-demo?state=overview`
- `/review-demo?state=manual`
- `/review-demo?state=automatic`
- `/review-demo?state=best`
- `/review-demo?state=price`
- `/review-demo?state=limit`
