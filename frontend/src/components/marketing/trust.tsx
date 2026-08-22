import { ShieldCheck } from "lucide-react";

import { content } from "@/components/marketing/content";

export function Trust() {
  return (
    <section className="bg-secondary/40 py-20">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-6 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary">
          <ShieldCheck className="h-6 w-6" />
        </span>
        <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          {content.trust.title}
        </h2>
        <p className="text-muted-foreground">{content.trust.desc}</p>
      </div>
    </section>
  );
}
