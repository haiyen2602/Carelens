import { content } from "@/components/marketing/content";

export function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-secondary/40 py-20">
      <div className="mx-auto max-w-6xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            {content.howItWorks.title}
          </h2>
          <p className="mt-3 text-muted-foreground">{content.howItWorks.subtitle}</p>
        </div>

        <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {content.howItWorks.steps.map((s) => (
            <li key={s.step} className="surface-card relative p-6 pt-8">
              <span className="absolute -top-4 left-6 grid h-8 w-8 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                {s.step}
              </span>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{s.desc}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
