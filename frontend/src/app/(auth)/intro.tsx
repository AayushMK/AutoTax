import { ArrowLeftRight, Landmark, Scale } from "lucide-react";
import Link from "next/link";

import styles from "./auth.module.css";

export function Brand() {
  return (
    <Link href="/" className={styles.brand}>
      <span className={styles.brandMark} aria-hidden="true">A</span>
      <span>
        <span className={styles.brandName}>AutoTax</span>{" "}
        <span className={styles.brandSub} lang="ne">कर हिसाब</span>
      </span>
    </Link>
  );
}

export function Intro() {
  return (
    <section className={styles.intro} aria-label="About AutoTax">
      <p className={styles.pitch}>Salary tax worked out line by line, from the Finance Act.</p>
      <div className={styles.sum} aria-label="Example payslip">
        <div><span>USD 1,800 at NRB buying 152.41</span><span>2,74,338.00</span></div>
        <div><span>SSF, 11% of basic</span><span>−25,147.65</span></div>
        <div><span>CIT</span><span>−5,000.00</span></div>
        <div><span>TDS this month</span><span>−35,774.82</span></div>
        <div className={styles.total}><span>Net pay, Shrawan 2083</span><span>2,08,415.53</span></div>
        <cite>Each line cites the section of the Act it comes from.</cite>
      </div>
      <ul className={styles.points}>
        <li>
          <span className={styles.ptIcon}><Scale size={16} /></span>
          <span><strong>Every figure cites the law</strong>Slabs, caps and reliefs come from versioned rule files, not hard-coded numbers.</span>
        </li>
        <li>
          <span className={styles.ptIcon}><ArrowLeftRight size={16} /></span>
          <span><strong>USD salaries at NRB rates</strong>Converted on each payment date, with the rate recorded on the payslip.</span>
        </li>
        <li>
          <span className={styles.ptIcon}><Landmark size={16} /></span>
          <span><strong>SSF, CIT and TDS by month and year</strong>Ready for remittance and the IRD TDS sheet.</span>
        </li>
      </ul>
    </section>
  );
}
