export type Finding={productId:string;productTitle:string;rule:string;evidence:string;detail:string};
export function makeMeta(shortName:string,exportSlug:string,lead:string,entityKind:"product"|"collection"="product"){
  return {shortName,exportSlug,readonlyLabel:"Read-only · Catalog QA",
    eyebrow:"CATALOG QA / REVIEW",headline:shortName,lead,
    sidebarHelp:"Inspect flagged items and decide what to review.",
    readOnlyNote:"The audit only reads merchant data; it never changes catalog content.",
    panelTitle:"Catalog findings",emptyCopy:"No matching issues were found in this batch.",
    entityKind} as const;
}
export function finish(rows:any[],findings:Finding[],skipped:string[]=[]){
  findings.sort((a,b)=>a.productTitle.localeCompare(b.productTitle));
  return {products:rows.length,findings,skipped};
}
export function csvFor(findings:Finding[],rules:Record<string,{label:string;advice:string}>){
  const safe=(v:unknown)=>{
    const s=String(v??"");const escaped=/^[\s]*[=+@\-\t\r\n]/.test(s)?"'"+s:s;
    return '"'+escaped.replace(/"/g,'""')+'"';
  };
  return "\uFEFF"+[["Priority","Item","Admin ID","Issue","Evidence","Recommendation"],
    ...findings.map(f=>["Review",f.productTitle,f.productId,rules[f.rule]?.label||f.rule,
      f.evidence,rules[f.rule]?.advice||f.detail])].map(row=>row.map(safe).join(",")).join("\r\n");
}
