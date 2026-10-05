# PAL Collection Ratio Guard — App Store submission draft

## Listing identity
- App name: PAL Collection Ratio Guard
- Primary language: English
- Intended public plan: US$4.99 per month
- Trial: 7 days
- Admin experience: non-embedded
- Required scopes: read_products
- Protected customer data: not used

## App introduction
Find collection images whose aspect ratios differ from the dominant catalog pattern.

## App details
PAL Collection Ratio Guard is a read-only collection image audit. It reads collection image dimensions, groups common aspect ratios, identifies the dominant observed ratio, flags different ratio groups, and exports a diagnostic CSV. The app never uploads, crops, or edits collection images.

## Feature bullets
1. Group collection images by practical aspect-ratio buckets.
2. Identify the dominant observed collection-image ratio.
3. Flag collections whose image ratio differs from the dominant group.
4. Export a diagnostic CSV with direct Shopify Admin collection links.

## Reviewer test steps
1. Install and approve only read_products.
2. Create several collections with square images.
3. Create one collection with a 16:9 image and one with a 3:4 image.
4. Run the audit and confirm the dominant ratio and outliers.
5. Confirm image dimensions and ratio groups match the source images.
6. Open a collection link and confirm it resolves to the matching Shopify Admin collection.
7. Export the CSV and confirm dimensions, ratio group, and admin link are included.
8. Run the audit again and confirm no collection images are changed.
9. Visit /privacy, /terms, /support, and /review-demo without Shopify authentication.
