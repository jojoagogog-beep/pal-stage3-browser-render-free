export const appMeta = {
 shortName: "Description A11y Guard", exportSlug: "description-accessibility",
 readonlyLabel: "Read-only · Accessibility QA", eyebrow: "CATALOG QA / ACCESSIBILITY",
 headline: "Find accessibility issues in product descriptions.",
 lead: "Review missing image alternatives, ambiguous links, and heading-level skips in the current product batch without changing catalog content.",
 sidebarHelp: "Choose an accessibility issue to review.", readOnlyNote: "The audit only reads merchant product descriptions; it never changes data.",
 panelTitle: "Description accessibility findings", emptyCopy: "No description accessibility issues were found in this batch."
} as const;

import { parseFragment, type DefaultTreeAdapterMap } from 'parse5';
export type Product = { id: string; title: string; descriptionHtml: string };
export const rules = {
  'missing-alt': { label: 'Image missing alt', priority: 'High', advice: 'Add an accurate alt attribute for meaningful images. Use alt="" only when the image is decorative.' },
  'empty-link': { label: 'Empty link', priority: 'High', advice: 'Give this link a descriptive accessible name that explains its destination.' },
  'heading-skip': { label: 'Skipped heading level', priority: 'Review', advice: 'Review the heading hierarchy and use consecutive levels for nested sections.' },
  'generic-link': { label: 'Generic link text', priority: 'Review', advice: 'Replace generic wording with a description of the link destination or purpose.' },
} as const;
export type Rule = keyof typeof rules;
export type Finding = { productId: string; productTitle: string; rule: Rule; evidence: string; line: number; column: number; detail: string };
export type Audit = { products: number; findings: Finding[]; skipped: string[] };
type Node = DefaultTreeAdapterMap['node'];
type Element = DefaultTreeAdapterMap['element'];
const attr = (n: Element, name: string) => n.attrs.find(a => a.name === name)?.value;
function textContent(n: Node): string {
  if ('value' in n) return n.value;
  if ('tagName' in n && (['script','style','template'].includes(n.tagName) || attr(n,'aria-hidden') === 'true' || attr(n,'hidden') !== undefined)) return '';
  if ('tagName' in n && n.tagName === 'img') return attr(n,'alt') || '';
  return 'childNodes' in n ? n.childNodes.map(textContent).join('') : '';
}
export function auditCatalog(products: Product[]): Audit {
  const findings: Finding[] = [], skipped: string[] = [];
  for (const p of products) {
    if (p.descriptionHtml.length > 250_000) { skipped.push(p.title); continue; }
    const root = parseFragment(p.descriptionHtml, { sourceCodeLocationInfo: true });
    let previousHeading = 0;
    const nodes: Element[] = [], stack: Node[] = [...root.childNodes].reverse();
    while (stack.length) {
      const n = stack.pop()!;
      if ('tagName' in n) {
        if (['script','style','template'].includes(n.tagName) || attr(n,'hidden') !== undefined || attr(n,'aria-hidden') === 'true') continue;
        nodes.push(n);
      }
      if ('childNodes' in n) stack.push(...[...n.childNodes].reverse());
    }
    const ids = new Map(nodes.filter(n => attr(n,'id')).map(n => [attr(n,'id')!, n]));
    const name = (n: Element) => {
      const refs = attr(n,'aria-labelledby')?.trim().split(/\s+/).map(id => ids.get(id)).filter((v):v is Element => Boolean(v));
      return (refs?.length ? refs.map(textContent).join(' ') : attr(n,'aria-label') || textContent(n) || attr(n,'title') || '').replace(/[\s\u200b-\u200d\ufeff]+/g,' ').trim();
    };
    const add = (n: Element, rule: Rule, detail: string) => {
      const loc = n.sourceCodeLocation;
      if (!loc) return;
      findings.push({ productId:p.id, productTitle:p.title, rule, detail, line:loc.startLine, column:loc.startCol, evidence:p.descriptionHtml.slice(loc.startOffset, loc.endOffset) });
    };
    for (const n of nodes) {
      if (n.tagName === 'img' && attr(n,'alt') === undefined) add(n,'missing-alt','The inline image has no alt attribute.');
      if (/^h[1-6]$/.test(n.tagName)) {
        const level = Number(n.tagName[1]);
        if (previousHeading && level > previousHeading + 1) add(n,'heading-skip',`Heading jumps from H${previousHeading} to H${level}.`);
        previousHeading = level;
      }
      if (n.tagName === 'a' && attr(n,'href') !== undefined) {
        const label = name(n);
        if (!label) add(n,'empty-link','The link has no detectable accessible name.');
        else if (/^(click here|here|read more|learn more|more|link|details)([.!…]+)?$/i.test(label)) add(n,'generic-link',`“${label}” may not explain the destination out of context.`);
      }
    }
  }
  findings.sort((a,b) => (rules[a.rule].priority === 'High' ? 0 : 1) - (rules[b.rule].priority === 'High' ? 0 : 1) || a.productTitle.localeCompare(b.productTitle) || a.line-b.line || a.column-b.column);
  return { products: products.length, findings, skipped };
}
export function buildCsv(findings: Finding[]): string {
  const cell = (value: string|number) => { const s = String(value); return '"' + (/^[\s]*[=+@\-\t\r\n]/.test(s) ? "'" + s : s).replace(/"/g,'""') + '"'; };
  return '\ufeff' + [['Priority','Product','Product ID','Issue','Line','Column','Exact HTML evidence','Recommendation'], ...findings.map(f => [rules[f.rule].priority,f.productTitle,f.productId,rules[f.rule].label,f.line,f.column,f.evidence,rules[f.rule].advice])].map(row=>row.map(cell).join(',')).join('\r\n');
}
