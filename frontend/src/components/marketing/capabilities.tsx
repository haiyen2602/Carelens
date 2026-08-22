import { BellRing, Camera, MessageCircleQuestion, Siren } from "lucide-react";

import { content } from "@/components/marketing/content";

const ICONS = [BellRing, Camera, MessageCircleQuestion, Siren];

export function Capabilities() {
  return (
    <section id="capabilities" className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          {content.capabilities.title}
        </h2>
        <p className="mt-3 text-muted-foreground">{content.capabilities.subtitle}</p>
      </div>

      <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {content.capabilities.items.map((item, i) => {
          const Icon = ICONS[i];
          return (
            <div key={item.title} className="surface-card p-6">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent text-accent-foreground">
                <Icon className="h-5 w-5" />
              </span>
              <h3 className="mt-4 font-semibold">{item.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{item.desc}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
