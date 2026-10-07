import styles from "./stamp.module.css";

type Tone = "seal" | "moss" | "ink";

/** A rubber-stamp mark. Used for exactly two things: rule review state and a finalized run. */
export function Stamp({ tone, title, note }: { tone: Tone; title: string; note?: string }) {
  return (
    <span className={`${styles.stamp} ${styles[tone]}`} role="status">
      <span className={styles.title}>{title}</span>
      {note && <span className={styles.note}>{note}</span>}
    </span>
  );
}
