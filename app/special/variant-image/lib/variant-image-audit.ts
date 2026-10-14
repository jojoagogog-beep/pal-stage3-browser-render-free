export type VariantImageInput = {
  id: string;
  alt: string | null;
};

export type VariantInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  images: VariantImageInput[];
};

export type ProductInput = {
  id: string;
  legacyResourceId: string;
  title: string;
  variants: VariantInput[];
};

export type IssueKey = "missing_dedicated_image" | "duplicate_image_assignment";

export type IssueDefinition = {
  key: IssueKey;
  label: string;
  priority: "Review";
  priorityRank: number;
  recommendation: string;
};

export type DuplicateAssignment = {
  imageId: string;
  alt: string | null;
  variantIds: string[];
  variantTitles: string[];
};

export type ProductAudit = ProductInput & {
  issueKeys: IssueKey[];
  findings: string[];
  status:
    | "Covered"
    | "Mixed coverage"
    | "Duplicate assignments"
    | "Mixed coverage + duplicates"
    | "No variant images";
  variantsWithImages: number;
  variantsMissingImages: number;
  missingVariants: VariantInput[];
  duplicateAssignments: DuplicateAssignment[];
};

export type RankedIssue = IssueDefinition & {
  affectedProducts: number;
  affectedVariants: number;
};

export type AuditResult = {
  products: ProductAudit[];
  affectedProducts: ProductAudit[];
  rankedIssues: RankedIssue[];
  summary: {
    productsScanned: number;
    variantsScanned: number;
    productsWithIssues: number;
    mixedCoverageProducts: number;
    duplicateAssignmentProducts: number;
    variantsMissingImages: number;
    productsWithNoVariantImages: number;
  };
};

export const ISSUE_DEFINITIONS: Record<IssueKey, IssueDefinition> = {
  missing_dedicated_image: {
    key: "missing_dedicated_image",
    label: "Variant image coverage is mixed",
    priority: "Review",
    priorityRank: 100,
    recommendation:
      "Review variants without an assigned image and decide whether each should use dedicated media.",
  },
  duplicate_image_assignment: {
    key: "duplicate_image_assignment",
    label: "Image is assigned to multiple variants",
    priority: "Review",
    priorityRank: 80,
    recommendation:
      "Confirm whether the shared image is intentional before changing any variant media.",
  },
};

function uniqueById<T extends { id: string }>(values: T[]): T[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    if (seen.has(value.id)) return false;
    seen.add(value.id);
    return true;
  });
}

export function auditCatalog(products: ProductInput[]): AuditResult {
  const auditedProducts: ProductAudit[] = products.map((product) => {
    const variants = product.variants.map((variant) => ({
      ...variant,
      images: uniqueById(variant.images),
    }));
    const variantsWithImages = variants.filter(
      (variant) => variant.images.length > 0,
    ).length;
    const missingVariants = variants.filter(
      (variant) => variant.images.length === 0,
    );
    const hasMixedCoverage =
      variants.length > 1 &&
      variantsWithImages > 0 &&
      variantsWithImages < variants.length;

    const assignments = new Map<
      string,
      { alt: string | null; variants: VariantInput[] }
    >();
    for (const variant of variants) {
      for (const image of variant.images) {
        const assignment = assignments.get(image.id) ?? {
          alt: image.alt,
          variants: [],
        };
        assignment.variants.push(variant);
        assignments.set(image.id, assignment);
      }
    }

    const duplicateAssignments = [...assignments.entries()]
      .filter(([, assignment]) => assignment.variants.length > 1)
      .map(([imageId, assignment]) => ({
        imageId,
        alt: assignment.alt,
        variantIds: assignment.variants.map((variant) => variant.id),
        variantTitles: assignment.variants.map((variant) => variant.title),
      }));

    const issueKeys: IssueKey[] = [];
    const findings: string[] = [];
    if (hasMixedCoverage) {
      issueKeys.push("missing_dedicated_image");
      findings.push(
        `${missingVariants.length} of ${variants.length} variants have no assigned image while sibling variants do.`,
      );
    }
    if (duplicateAssignments.length > 0) {
      issueKeys.push("duplicate_image_assignment");
      findings.push(
        `${duplicateAssignments.length} image assignment${duplicateAssignments.length === 1 ? " is" : "s are"} shared across variants.`,
      );
    }

    let status: ProductAudit["status"] = "Covered";
    if (variants.length > 0 && variantsWithImages === 0) {
      status = "No variant images";
    } else if (hasMixedCoverage && duplicateAssignments.length > 0) {
      status = "Mixed coverage + duplicates";
    } else if (hasMixedCoverage) {
      status = "Mixed coverage";
    } else if (duplicateAssignments.length > 0) {
      status = "Duplicate assignments";
    }

    return {
      ...product,
      variants,
      issueKeys,
      findings,
      status,
      variantsWithImages,
      variantsMissingImages: missingVariants.length,
      missingVariants,
      duplicateAssignments,
    };
  });

  const affectedProducts = auditedProducts
    .filter((product) => product.issueKeys.length > 0)
    .sort(
      (a, b) =>
        b.issueKeys.length - a.issueKeys.length ||
        b.variantsMissingImages - a.variantsMissingImages ||
        a.title.localeCompare(b.title),
    );

  const rankedIssues = (Object.keys(ISSUE_DEFINITIONS) as IssueKey[])
    .map((key) => ({
      ...ISSUE_DEFINITIONS[key],
      affectedProducts: affectedProducts.filter((product) =>
        product.issueKeys.includes(key),
      ).length,
      affectedVariants:
        key === "missing_dedicated_image"
          ? affectedProducts.reduce(
              (total, product) => total + product.variantsMissingImages,
              0,
            )
          : affectedProducts.reduce(
              (total, product) =>
                total +
                product.duplicateAssignments.reduce(
                  (count, assignment) => count + assignment.variantIds.length,
                  0,
                ),
              0,
            ),
    }))
    .filter((issue) => issue.affectedProducts > 0)
    .sort((a, b) => b.priorityRank - a.priorityRank);

  return {
    products: auditedProducts,
    affectedProducts,
    rankedIssues,
    summary: {
      productsScanned: auditedProducts.length,
      variantsScanned: auditedProducts.reduce(
        (total, product) => total + product.variants.length,
        0,
      ),
      productsWithIssues: affectedProducts.length,
      mixedCoverageProducts: affectedProducts.filter((product) =>
        product.issueKeys.includes("missing_dedicated_image"),
      ).length,
      duplicateAssignmentProducts: affectedProducts.filter((product) =>
        product.issueKeys.includes("duplicate_image_assignment"),
      ).length,
      variantsMissingImages: affectedProducts.reduce(
        (total, product) => total + product.variantsMissingImages,
        0,
      ),
      productsWithNoVariantImages: auditedProducts.filter(
        (product) => product.status === "No variant images",
      ).length,
    },
  };
}

function csvCell(value: string | number) {
  let text = String(value).replaceAll("\r", " ").replaceAll("\n", " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function productAdminUrl(adminBaseUrl: string, productId: string) {
  return adminBaseUrl
    ? `${adminBaseUrl.replace(/\/$/, "")}/products/${encodeURIComponent(productId)}`
    : "";
}

export function buildAffectedProductsCsv(
  audit: AuditResult,
  adminBaseUrl: string,
) {
  const rows: Array<Array<string | number>> = [
    [
      "Finding",
      "Product",
      "Product admin URL",
      "Variant",
      "Assigned image count",
      "Shared image ID",
      "Details",
      "Recommended next step",
    ],
  ];

  for (const product of audit.affectedProducts) {
    if (product.issueKeys.includes("missing_dedicated_image")) {
      for (const variant of product.missingVariants) {
        rows.push([
          ISSUE_DEFINITIONS.missing_dedicated_image.label,
          product.title,
          productAdminUrl(adminBaseUrl, product.legacyResourceId),
          variant.title,
          0,
          "",
          `${product.variantsWithImages} of ${product.variants.length} sibling variants have assigned images.`,
          ISSUE_DEFINITIONS.missing_dedicated_image.recommendation,
        ]);
      }
    }

    for (const assignment of product.duplicateAssignments) {
      rows.push([
        ISSUE_DEFINITIONS.duplicate_image_assignment.label,
        product.title,
        productAdminUrl(adminBaseUrl, product.legacyResourceId),
        assignment.variantTitles.join(" | "),
        assignment.variantIds.length,
        assignment.imageId,
        `The same image is assigned to ${assignment.variantIds.length} variants.`,
        ISSUE_DEFINITIONS.duplicate_image_assignment.recommendation,
      ]);
    }
  }

  return (
    "\uFEFF" +
    rows.map((row) => row.map(csvCell).join(",")).join("\r\n") +
    "\r\n"
  );
}
