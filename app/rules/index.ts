import * as reviewVariant from './pal-variant-price-range-guard';
import * as reviewZero from './pal-zero-price-variant-guard';
import * as r00 from './pal-title-length-guard';
import * as r01 from './pal-title-word-count-guard';
import * as r02 from './pal-title-digit-guard';
import * as r03 from './pal-title-trailing-mark-guard';
import * as r04 from './pal-title-leading-space-guard';
import * as r05 from './pal-handle-length-guard';
import * as r06 from './pal-handle-format-guard';
import * as r07 from './pal-handle-digit-tail-guard';
import * as r08 from './pal-vendor-empty-guard';
import * as r09 from './pal-vendor-length-guard';
import * as r10 from './pal-vendor-symbol-guard';
import * as r11 from './pal-type-empty-guard';
import * as r12 from './pal-type-length-guard';
import * as r13 from './pal-tag-duplicate-guard';
import * as r14 from './pal-tag-whitespace-guard';
import * as r15 from './pal-tag-symbol-guard';
import * as r16 from './pal-tag-numeric-guard';
import * as r17 from './pal-tag-uppercase-guard';
import * as r18 from './pal-description-empty-guard';
import * as r19 from './pal-description-short-guard';
import * as r20 from './pal-description-long-guard';
import * as r21 from './pal-description-heading-guard';
import * as r22 from './pal-description-list-guard';
import * as r23 from './pal-description-script-guard';
import * as r24 from './pal-description-email-guard';
import * as r25 from './pal-description-phone-guard';
import * as r26 from './pal-description-image-count-guard';
import * as r27 from './pal-description-broken-link-guard';
import * as r28 from './pal-description-empty-anchor-guard';
import * as r29 from './pal-description-bold-guard';
import * as r30 from './pal-description-uppercase-guard';
import * as r31 from './pal-variant-empty-guard';
import * as r32 from './pal-variant-title-length-guard';
import * as r33 from './pal-variant-title-delimiter-guard';
import * as r34 from './pal-variant-sku-length-guard';
import * as r35 from './pal-variant-sku-symbol-guard';
import * as r36 from './pal-variant-sku-space-guard';
import * as r37 from './pal-variant-sku-case-guard';
import * as r38 from './pal-variant-sku-numeric-guard';
import * as r39 from './pal-barcode-length-guard';
import * as r40 from './pal-barcode-format-guard';
import * as r41 from './pal-barcode-space-guard';
import * as r42 from './pal-option-name-length-guard';
import * as r43 from './pal-option-value-case-guard';
import * as r44 from './pal-option-value-space-guard';
import * as r45 from './pal-option-value-empty-guard';
import * as r46 from './pal-compare-price-equal-guard';
import * as r47 from './pal-compare-price-format-guard';
import * as r48 from './pal-price-precision-guard';
import * as r49 from './pal-compare-zero-guard';
import * as r50 from './pal-barcode-checksum-guard';
import * as r51 from './pal-option-value-length-guard';
import * as r52 from './pal-option-delimiter-guard';

import * as r53 from './pal-product-image-alt-guard';
import * as r54 from './pal-collection-image-ratio-guard';
import * as r55 from './pal-collection-sort-guard';

import * as r56 from './pal-active-product-age-guard';
import * as r57 from './pal-shipping-weight-integrity-guard';
import * as reviewTemplate from './pal-product-template-guard';
import * as reviewCategory from './pal-category-attribute-coverage-guard';
import * as reviewMedia from './pal-product-media-count-guard';
import * as reviewDraft from './pal-stale-draft-product-guard';
import * as reviewDescription from './pal-product-description-guard';
import * as reviewCollectionContent from './pal-collection-content-guard';

export const ruleModules = {
  'pal-shipping-weight-integrity-guard': r57,
  'pal-product-template-guard': reviewTemplate,
  'pal-category-attribute-coverage-guard': reviewCategory,
  'pal-product-media-count-guard': reviewMedia,
  'pal-stale-draft-product-guard': reviewDraft,
  'pal-product-description-guard': reviewDescription,
  'pal-collection-content-guard': reviewCollectionContent,
  'pal-variant-price-range-guard': reviewVariant,
  'pal-zero-price-variant-guard': reviewZero,
  'pal-active-product-age-guard': r56,
  'pal-product-image-alt-guard': r53,
  'pal-collection-image-ratio-guard': r54,
  'pal-collection-sort-guard': r55,
  'pal-title-length-guard': r00,
  'pal-title-word-count-guard': r01,
  'pal-title-digit-guard': r02,
  'pal-title-trailing-mark-guard': r03,
  'pal-title-leading-space-guard': r04,
  'pal-handle-length-guard': r05,
  'pal-handle-format-guard': r06,
  'pal-handle-digit-tail-guard': r07,
  'pal-vendor-empty-guard': r08,
  'pal-vendor-length-guard': r09,
  'pal-vendor-symbol-guard': r10,
  'pal-type-empty-guard': r11,
  'pal-type-length-guard': r12,
  'pal-tag-duplicate-guard': r13,
  'pal-tag-whitespace-guard': r14,
  'pal-tag-symbol-guard': r15,
  'pal-tag-numeric-guard': r16,
  'pal-tag-uppercase-guard': r17,
  'pal-description-empty-guard': r18,
  'pal-description-short-guard': r19,
  'pal-description-long-guard': r20,
  'pal-description-heading-guard': r21,
  'pal-description-list-guard': r22,
  'pal-description-script-guard': r23,
  'pal-description-email-guard': r24,
  'pal-description-phone-guard': r25,
  'pal-description-image-count-guard': r26,
  'pal-description-broken-link-guard': r27,
  'pal-description-empty-anchor-guard': r28,
  'pal-description-bold-guard': r29,
  'pal-description-uppercase-guard': r30,
  'pal-variant-empty-guard': r31,
  'pal-variant-title-length-guard': r32,
  'pal-variant-title-delimiter-guard': r33,
  'pal-variant-sku-length-guard': r34,
  'pal-variant-sku-symbol-guard': r35,
  'pal-variant-sku-space-guard': r36,
  'pal-variant-sku-case-guard': r37,
  'pal-variant-sku-numeric-guard': r38,
  'pal-barcode-length-guard': r39,
  'pal-barcode-format-guard': r40,
  'pal-barcode-space-guard': r41,
  'pal-option-name-length-guard': r42,
  'pal-option-value-case-guard': r43,
  'pal-option-value-space-guard': r44,
  'pal-option-value-empty-guard': r45,
  'pal-compare-price-equal-guard': r46,
  'pal-compare-price-format-guard': r47,
  'pal-price-precision-guard': r48,
  'pal-compare-zero-guard': r49,
  'pal-barcode-checksum-guard': r50,
  'pal-option-value-length-guard': r51,
  'pal-option-delimiter-guard': r52,
} as const;
export type AppSlug = keyof typeof ruleModules;
