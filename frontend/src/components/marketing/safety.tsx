import { CheckCircle2 } from "lucide-react";

import { content } from "@/components/marketing/content";

export function Safety() {
  return (
    <section id="safety" className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          {content.safety.title}
        </h2>
        <p className="mt-3 text-muted-foreground">{content.safety.subtitle}</p>
      </div>

      <div className="mx-auto mt-12 grid max-w-3xl gap-4 sm:grid-cols-2">
        {content.safety.items.map((item) => (
          <div key={item.title} className="flex gap-3 rounded-xl bg-muted p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <h3 className="text-sm font-semibold">{item.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
