import Link from "next/link";

import styles from "./auth.module.css";
import { Floats } from "./floats";

/** Page frame for the sign-in pages: top bar, floating tiles, centred form. */
export function AuthFrame({ topLink, children }: { topLink: { href: string; label: string }; children: React.ReactNode }) {
  return (
    <div className={styles.wrap}>
      <header className={styles.topbar}>
        <Link href="/" className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">A</span>
          <span className={styles.brandName}>AutoTax</span>
          <span className={styles.brandSub} lang="ne">कर हिसाब</span>
        </Link>
        <Link href={topLink.href} className={styles.topLink}>{topLink.label}</Link>
      </header>
      <Floats />
      <main className={styles.center}>{children}</main>
    </div>
  );
}

export function Headline({ before, pill, after, sub }: { before: string; pill: string; after: string; sub: string }) {
  return (
    <>
      <h1 className={styles.headline}>
        {before} <span className={styles.pill}>{pill}</span>{after}
      </h1>
      <p className={styles.sub}>{sub}</p>
    </>
  );
}
