import type { ReactNode } from "react";

type PanelProps = {
  children: ReactNode;
  title: string;
};

export function Panel({ children, title }: PanelProps) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
