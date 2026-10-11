export const TITLE_REVIEW_LIMIT = 70;
export const DESCRIPTION_PREVIEW_POINT = 160;
export const DESCRIPTION_REVIEW_LIMIT = 320;

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  description: string;
  seoTitle: string | null;
  seoDescription: string | null;
};

export type IssueKey =
  | "partial_customization"
  | "both_fields_fallback"
  | "missing_description_source"
  | "title_fallback_long"
  | "description_fallback_long"
  | "description_cutoff_risk";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "High" | "Medium" | "Review";
  priorityRank: number;
  recommendation: string;
};

export type ProductAudit = ProductInput & {
  blankSeoTitle: boolean;
  blankSeoDescription: boolean;
  estimatedTitleFallback: string;
  estimatedDescriptionFallback: string;
  titleFallbackLength: number;
  descriptionFallbackLength: number;
  issueKeys: IssueKey[];
  findings: string[];
  status:
    | "Partial custom SEO"
    | "Both fields use fallback"
    | "Custom SEO complete";
};

export type RankedIssue = IssueDefinition & { affectedProducts: number };

export type AuditResult = {
  products: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    productsUsingFallback: number;
    partiallyCustomized: number;
    bothFieldsFallback: number;
    fallbackLengthReviews: number;
    customSeoComplete: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  partial_customization: {
    key: "partial_customization",
    label: "Only one custom SEO field is set",
    priority: "High",
    priorityRank: 100,
    recommendation:
      "Review the blank field beside the existing custom field and decide whether to add matching custom metadata.",
  },
  missing_description_source: {
    key: "missing_description_source",
    label: "Description fallback source is blank",
    priority: "High",
    priorityRank: 95,
    recommendation:
      "Add a product description or a custom SEO description so the estimated fallback is not empty.",
  },
  both_fields_fallback: {
    key: "both_fields_fallback",
    label: "Both custom SEO fields are blank",
    priority: "Medium",
    priorityRank: 80,
    recommendation:
      "Review the estimated title and description sources, then add custom SEO text if the fallback does not match merchant intent.",
  },
  title_fallback_long: {
    key: "title_fallback_long",
    label: `Title fallback is over ${TITLE_REVIEW_LIMIT} characters`,
    priority: "Medium",
    priorityRank: 70,
    recommendation:
      "Review the product title as an SEO title source and consider a shorter custom SEO title if needed.",
  },
  description_fallback_long: {
    key: "description_fallback_long",
    label: `Description fallback is over ${DESCRIPTION_REVIEW_LIMIT} characters`,
    priority: "Medium",
    priorityRank: 65,
    recommendation:
      "Review the product description and consider a focused custom SEO description if the source is too long for the intended message.",
  },
  description_cutoff_risk: {
    key: "description_cutoff_risk",
    label: `Fallback crosses the ${DESCRIPTION_PREVIEW_POINT}-character review point mid-thought`,
    priority: "Review",
    priorityRank: 50,
    recommendation:
      "Review the fallback preview and consider custom SEO text that reaches a natural stopping point sooner.",
  },
};

function normalize(value: string | null | undefined) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

function crossesPreviewPointMidThought(value: string) {
  if (value.length <= DESCRIPTION_PREVIEW_POINT) return false;

  const before = value.slice(0, DESCRIPTION_PREVIEW_POINT);
  const after = value.slice(DESCRIPTION_PREVIEW_POINT);
  const lastCharacter = before.at(-1) ?? "";
  const nextCharacter = after.at(0) ?? "";
  const splitsWord = /[\p{L}\p{N}]/u.test(lastCharacter) && /[\p{L}\p{N}]/u.test(nextCharacter);
  const endsAtSentence = /[.!?]["')\]]?\s*$/u.test(before);

  return splitsWord || !endsAtSentence;
}

function statusFor(blankTitle: boolean, blankDescription: boolean): ProductAudit["status"] {
  if (blankTitle && blankDescription) return "Both fields use fallback";
  if (blankTitle !== blankDescription) return "Partial custom SEO";
  return "Custom SEO complete";
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const audited = products.map<ProductAudit>((product) => {
    const seoTitle = normalize(product.seoTitle);
    const seoDescription = normalize(product.seoDescription);
    const estimatedTitleFallback = normalize(product.title);
    const estimatedDescriptionFallback = normalize(product.description);
    const blankSeoTitle = !seoTitle;
    const blankSeoDescription = !seoDescription;
    const issueKeys: IssueKey[] = [];
    const findings: string[] = [];

    if (blankSeoTitle !== blankSeoDescription) {
      issueKeys.push("partial_customization");
      findings.push(
        blankSeoTitle
          ? "The SEO description is customized, while the SEO title is blank."
          : "The SEO title is customized, while the SEO description is blank.",
      );
    }

    if (blankSeoTitle && blankSeoDescription) {
      issueKeys.push("both_fields_fallback");
      findings.push("Both custom SEO fields are blank.");
    }

    if (blankSeoDescription && !estimatedDescriptionFallback) {
      issueKeys.push("missing_description_source");
      findings.push("The custom SEO description and product description are both blank.");
    }

    if (blankSeoTitle && estimatedTitleFallback.length > TITLE_REVIEW_LIMIT) {
      issueKeys.push("title_fallback_long");
      findings.push(
        `The estimated title fallback is ${estimatedTitleFallback.length} characters.`,
      );
    }

    if (
      blankSeoDescription &&
      estimatedDescriptionFallback.length > DESCRIPTION_REVIEW_LIMIT
    ) {
      issueKeys.push("description_fallback_long");
      findings.push(
        `The estimated description fallback is ${estimatedDescriptionFallback.length} characters.`,
      );
    }

    if (
      blankSeoDescription &&
      crossesPreviewPointMidThought(estimatedDescriptionFallback)
    ) {
      issueKeys.push("description_cutoff_risk");
      findings.push(
        `The estimated description crosses the ${DESCRIPTION_PREVIEW_POINT}-character review point without a clean ending.`,
      );
    }

    return {
      ...product,
      seoTitle,
      seoDescription,
      blankSeoTitle,
      blankSeoDescription,
      estimatedTitleFallback,
      estimatedDescriptionFallback,
      titleFallbackLength: estimatedTitleFallback.length,
      descriptionFallbackLength: estimatedDescriptionFallback.length,
      issueKeys: unique(issueKeys),
      findings: unique(findings),
      status: statusFor(blankSeoTitle, blankSeoDescription),
    };
  });

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => ({
      ...ISSUE_DEFINITIONS[key],
      affectedProducts: audited.filter((product) =>
        product.issueKeys.includes(key),
      ).length,
    }))
    .filter((issue) => issue.affectedProducts > 0)
    .sort(
      (a, b) =>
        b.priorityRank - a.priorityRank ||
        b.affectedProducts - a.affectedProducts ||
        a.label.localeCompare(b.label),
    );

  const priorityScore = (product: ProductAudit) =>
    Math.max(
      0,
      ...product.issueKeys.map((key) => ISSUE_DEFINITIONS[key].priorityRank),
    );

  return {
    products: audited.sort(
      (a, b) =>
        priorityScore(b) - priorityScore(a) ||
        b.issueKeys.length - a.issueKeys.length ||
        a.title.localeCompare(b.title),
    ),
    rankedIssues,
    summary: {
      productsScanned: audited.length,
      productsUsingFallback: audited.filter(
        (product) => product.blankSeoTitle || product.blankSeoDescription,
      ).length,
      partiallyCustomized: audited.filter(
        (product) => product.blankSeoTitle !== product.blankSeoDescription,
      ).length,
      bothFieldsFallback: audited.filter(
        (product) => product.blankSeoTitle && product.blankSeoDescription,
      ).length,
      fallbackLengthReviews: audited.filter((product) =>
        product.issueKeys.some((key) =>
          [
            "title_fallback_long",
            "description_fallback_long",
            "description_cutoff_risk",
          ].includes(key),
        ),
      ).length,
      customSeoComplete: audited.filter(
        (product) => !product.blankSeoTitle && !product.blankSeoDescription,
      ).length,
    },
  };
}

function protectCsvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function safeShopDomain(shopDomain: string) {
  const value = shopDomain.trim().toLowerCase();
  return /^[a-z0-9][a-z0-9-]*\.myshopify\.com$/.test(value)
    ? value
    : "admin.shopify.com";
}

export function productAdminUrl(shopDomain: string, legacyResourceId: string) {
  const shop = safeShopDomain(shopDomain);
  const productId = encodeURIComponent(legacyResourceId);
  return shop === "admin.shopify.com"
    ? `https://${shop}/products/${productId}`
    : `https://${shop}/admin/products/${productId}`;
}

export function buildRemediationCsv(audit: AuditResult, shopDomain: string) {
  const rows: Array<Array<string | number>> = [
    [
      "Priority",
      "Product",
      "Product admin link",
      "Custom SEO title",
      "Custom SEO description",
      "Estimated title fallback",
      "Title fallback characters",
      "Estimated description fallback",
      "Description fallback characters",
      "Findings",
      "Recommended next step",
    ],
  ];

  for (const product of audit.products) {
    if (!product.blankSeoTitle && !product.blankSeoDescription) continue;

    const definitions = product.issueKeys
      .map((key) => ISSUE_DEFINITIONS[key])
      .sort((a, b) => b.priorityRank - a.priorityRank);
    const highestPriority = definitions[0]?.priority ?? "Review";
    rows.push([
      highestPriority,
      product.title || "Untitled product",
      productAdminUrl(shopDomain, product.legacyResourceId),
      product.blankSeoTitle ? "Blank — estimated fallback" : "Set",
      product.blankSeoDescription ? "Blank — estimated fallback" : "Set",
      product.blankSeoTitle ? product.estimatedTitleFallback : "Not used",
      product.blankSeoTitle ? product.titleFallbackLength : 0,
      product.blankSeoDescription
        ? product.estimatedDescriptionFallback
        : "Not used",
      product.blankSeoDescription ? product.descriptionFallbackLength : 0,
      product.findings.join(" ") || "Custom field is blank; review fallback source.",
      unique(definitions.map((definition) => definition.recommendation)).join(
        " ",
      ),
    ]);
  }

  return `\uFEFF${rows
    .map((row) => row.map(protectCsvCell).join(","))
    .join("\r\n")}\r\n`;
}
