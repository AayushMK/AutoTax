import Link from "next/link";

import { Stamp } from "@/components/stamp";

import styles from "./auth.module.css";

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

/** The tiles around the form: real things AutoTax works out. Decorative only. */
function Floats() {
  return (
    <div aria-hidden="true">
      <div className={`${styles.float} ${styles.f1} hue-blue`}>
        <small>NRB buying rate</small>
        <b>USD 1 = 152.41</b>
        <i>14 Aug 2026</i>
      </div>
      <div className={`${styles.float} ${styles.f2} hue-green`}>
        <small>SSF, 31% of basic</small>
        <b>11% + 20%</b>
        <i>employee + employer</i>
      </div>
      <div className={`${styles.float} ${styles.f3} hue-purple`}>
        <small><span className={styles.dot} />Shrawan 2083</small>
        <b>Net 2,08,415.53</b>
        <i>TDS 35,774.82</i>
      </div>
      <div className={`${styles.float} ${styles.f4} hue-orange`}>
        <small>TDS this month</small>
        <b>35,774.82</b>
        <i>spread over the rest of the year</i>
      </div>
      <div className={`${styles.float} ${styles.f5} hue-pink`}>
        <small>CIT</small>
        <b>Up to 5 lakh</b>
        <i>with SSF, or a third of income</i>
      </div>
      <div className={styles.f6}>
        <Stamp tone="moss" title="Finalized" note="Shrawan 2083" />
      </div>
    </div>
  );
}
