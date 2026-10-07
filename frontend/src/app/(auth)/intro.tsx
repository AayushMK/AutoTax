import styles from "./auth.module.css";

export function Intro() {
  return (
    <section className={styles.intro}>
      <span className={styles.mark}>AutoTax</span>
      <p className={styles.claim}>Salary tax worked out line by line, from the Finance Act.</p>
      <div className={styles.sum} aria-label="Example calculation">
        <div><span>USD 1,800 at NRB buying 152.41</span><span>2,74,338.00</span></div>
        <div><span>SSF, 11% of basic</span><span>−25,147.65</span></div>
        <div><span>CIT</span><span>−5,000.00</span></div>
        <div><span>TDS this month</span><span>−35,774.82</span></div>
        <div className={styles.total}><span>Net pay, Shrawan 2083</span><span>2,08,415.53</span></div>
        <cite>Each line cites the section of the Act it comes from.</cite>
      </div>
    </section>
  );
}
