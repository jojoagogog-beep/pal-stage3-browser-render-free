import type { ReactNode } from "react";
import styles from "./public-page.module.css";

type PublicPageProps = {
  title: string;
  intro: string;
  children: ReactNode;
};

export function PublicPage({ title, intro, children }: PublicPageProps) {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/">
          PAL Handle Title Drift Guard
        </a>
        <span>Practical AI Lab</span>
      </header>
      <article className={styles.article}>
        <p className={styles.eyebrow}>PUBLIC APP INFORMATION</p>
        <h1>{title}</h1>
        <p className={styles.intro}>{intro}</p>
        {children}
        <p className={styles.updated}>Last updated: October 4, 2026</p>
      </article>
      <nav className={styles.links} aria-label="App information">
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href="/support">Support</a>
      </nav>
    </main>
  );
}
