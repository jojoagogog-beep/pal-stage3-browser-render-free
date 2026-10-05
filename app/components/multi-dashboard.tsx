import { useState } from "react";
import styles from "./description-dashboard.module.css";

type Definition = {
  appMeta: any;
  rules: Record<string, { label: string; priority: string; advice: string }>;
  buildCsv: (findings: any[]) => string;
};
type Props = {
  definition: Definition;
  audit: any;
  demo?: boolean;
  initialFilter?: string;
  scannedAt?: string;
  nextCursor?: string | null;
  laterBatch?: boolean;
  busy?: boolean;
  onRefresh?: () => void;
  onNext?: () => void;
  onRestart?: () => void;
};

export function MultiDashboard({
  definition,audit,demo=false,initialFilter="all",nextCursor,laterBatch,busy,onRefresh,onNext,onRestart
}:Props){
  const { appMeta, rules, buildCsv } = definition;
  const [filter,setFilter]=useState(initialFilter==="worklist"?"all":initialFilter);
  const [search,setSearch]=useState("");
  const [tab,setTab]=useState(initialFilter==="worklist"?"worklist":"findings");
  const findings=(audit.findings||[]).filter((f:any)=>(filter==="all"||f.rule===filter)&&String(f.productTitle||"").toLowerCase().includes(search.toLowerCase()));
  const [selected,setSelected]=useState<string|null>(null);
  const key=(f:any)=>`${f.productId}:${f.rule}:${f.evidence}`;
  const active=findings.find((f:any)=>key(f)===selected)||findings[0];

  function download(){
    const url=URL.createObjectURL(new Blob([buildCsv(findings)],{type:"text/csv;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=`${appMeta.exportSlug}-${demo?"demo-":""}worklist.csv`;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  return <main className={styles.shell}>
    <header className={styles.top}>
      <div className={styles.brand}><span className={styles.mark}>PAL</span><span>{appMeta.shortName}</span></div>
      <span className={styles.readonly}>{appMeta.readonlyLabel}</span>
    </header>
    <div className={styles.body}>
      <div className={styles.heading}><div>
        <p className={styles.eyebrow}>{appMeta.eyebrow}</p><h1>{appMeta.headline}</h1><p className={styles.lead}>{appMeta.lead}</p>
      </div></div>
      <div className={styles.context}>
        <span>{demo?"Demo catalog · Illustrative sample data":"Live catalog · "+(laterBatch?"Later product batch":"First product batch")}</span>
        <span>{demo?"No store connection":`${audit.products} products in this batch`}</span>
      </div>
      <div className={styles.controls}>
        <nav aria-label="Audit views">
          <button className={tab==="findings"?styles.active:""} onClick={()=>setTab("findings")}>Review findings</button>
          <button className={tab==="worklist"?styles.active:""} onClick={()=>setTab("worklist")}>Remediation worklist</button>
        </nav>
        <div>
          <button onClick={onRefresh||(()=>{setFilter("all");setSearch("");setSelected(null);})} disabled={busy}>{busy?"Scanning…":demo?"Reset demo":"Rescan batch"}</button>{" "}
          <button className={styles.primary} onClick={download} disabled={!findings.length}>Export filtered CSV ↓</button>
        </div>
      </div>
      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <h2>Focus your review</h2><p>{appMeta.sidebarHelp}</p>
          <button aria-pressed={filter==="all"} onClick={()=>setFilter("all")}>All findings</button>
          {Object.entries(rules).map(([id,rule])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{rule.label}</button>)}
          <div className={styles.note}><b>Read-only by design.</b><p>{appMeta.readOnlyNote}</p></div>
        </aside>
        <section className={styles.panel} aria-label="Audit results">
          <div className={styles.panelTitle}><h2>{tab==="worklist"?"A clear handoff for your catalog team":appMeta.panelTitle}</h2>
            <label>Find a product<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search product titles" type="search"/></label>
          </div>
          {audit.skipped?.length>0&&<p role="alert" className={styles.warning}>Not checked: {audit.skipped.join(", ")}.</p>}
          {nextCursor&&<p className={styles.warning}>More products remain. This view and its export cover only the current batch.</p>}
          {!findings.length ? <div className={styles.empty}>
              <h3>{search||filter!=="all"?"No matching findings":audit.products===0?"Your catalog is empty":"No issues detected by these checks"}</h3>
              <p>{search||filter!=="all"?"Try another filter or product title.":appMeta.emptyCopy}</p>
            </div>
            : tab==="worklist"
              ? <div className={styles.tableWrap}><table><thead><tr><th>Priority</th><th>Product / issue</th><th>Next step</th></tr></thead>
                  <tbody>{findings.map((f:any)=><tr key={key(f)}>
                    <td><span className={rules[f.rule]?.priority==="High"?styles.high:styles.review}>{rules[f.rule]?.priority||"Review"}</span></td>
                    <td><b>{f.productTitle}</b><p>{rules[f.rule]?.label}</p></td><td>{rules[f.rule]?.advice}</td>
                  </tr>)}</tbody></table><p className={styles.caption}>CSV includes product IDs, evidence, issue type, and recommendation. Current filters apply.</p>
                </div>
              : <div className={styles.results}>
                  <div className={styles.list}>{findings.map((f:any)=><button key={key(f)} onClick={()=>setSelected(key(f))} aria-pressed={active===f}>
                    <span className={rules[f.rule]?.priority==="High"?styles.high:styles.review}>{rules[f.rule]?.priority||"Review"}</span>
                    <b>{f.productTitle}</b><span>{rules[f.rule]?.label}</span></button>)}</div>
                  {active&&<article className={styles.evidence}><p className={styles.eyebrow}>CATALOG EVIDENCE</p>
                    <h3>{rules[active.rule]?.label}</h3><p>{active.detail}</p><pre><code>{active.evidence}</code></pre>
                    <h4>Suggested review</h4><p>{rules[active.rule]?.advice}</p>
                    {demo?<span className={styles.demoLink}>Product editor links appear in a connected store.</span>:<a target="_top" href={`shopify://admin/products/${String(active.productId).split("/").pop()}`}>Open product in admin ↗</a>}
                  </article>}
                </div>}
          <div className={styles.footer}><span>High-priority findings appear first. Priorities are review guidance.</span>
            <div>{laterBatch&&<button onClick={onRestart}>First batch</button>} {onNext&&<button onClick={onNext}>Next product batch →</button>}</div>
          </div>
        </section>
      </div>
    </div>
  </main>;
}
