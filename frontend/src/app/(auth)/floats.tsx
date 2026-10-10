"use client";

import { useRef, useState } from "react";

import { Stamp } from "@/components/stamp";

import styles from "./auth.module.css";

type Offset = { x: number; y: number };

/** The tiles around the sign-in form. Decorative, and draggable for fun. */
export function Floats() {
  const [last, setLast] = useState<number | null>(null); // the tile dropped most recently stays on top
  const tile = (i: number, className: string, hue: string, children: React.ReactNode) => (
    <Draggable key={i} className={`${styles.float} ${className} hue-${hue}`} onGrab={() => setLast(i)} onTop={last === i}>
      {children}
    </Draggable>
  );
  return (
    <div aria-hidden="true">
      {tile(1, styles.f1, "blue", <><small>NRB buying rate</small><b>USD 1 = 152.41</b><i>14 Aug 2026</i></>)}
      {tile(2, styles.f2, "green", <><small>SSF, 31% of basic</small><b>11% + 20%</b><i>employee + employer</i></>)}
      {tile(3, styles.f3, "purple", <><small><span className={styles.dot} />Payslip ready</small><b>Bhadra 2083</b><i>addition, deduction, net</i></>)}
      {tile(4, styles.f4, "orange", <><small>IRD TDS sheet</small><b>Ready to download</b><i>PAN, name, every month</i></>)}
      {tile(5, styles.f5, "pink", <><small>Your calendar</small><b>Nepali or English months</b><i>July split at Shrawan 1</i></>)}
      <Draggable className={styles.f6} onGrab={() => setLast(6)} onTop={last === 6}>
        <Stamp tone="moss" title="Finalized" note="Shrawan 2083" />
      </Draggable>
    </div>
  );
}

function Draggable({ className, children, onGrab, onTop }: {
  className: string;
  children: React.ReactNode;
  onGrab: () => void;
  onTop: boolean;
}) {
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const start = useRef<{ px: number; py: number; x: number; y: number } | null>(null);

  return (
    <div
      className={`${className} ${styles.draggable} ${dragging ? styles.dragging : ""}`}
      style={{ "--dx": `${offset.x}px`, "--dy": `${offset.y}px`, zIndex: dragging ? 40 : onTop ? 30 : undefined } as React.CSSProperties}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = { px: e.clientX, py: e.clientY, x: offset.x, y: offset.y };
        setDragging(true);
        onGrab();
      }}
      onPointerMove={(e) => {
        const s = start.current;
        if (s) setOffset({ x: s.x + e.clientX - s.px, y: s.y + e.clientY - s.py });
      }}
      onPointerUp={() => {
        start.current = null;
        setDragging(false);
      }}
      onPointerCancel={() => {
        start.current = null;
        setDragging(false);
      }}
    >
      {children}
    </div>
  );
}
