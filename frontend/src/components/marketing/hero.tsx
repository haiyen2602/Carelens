import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { CapyMascot } from "@/components/mascot/capy-mascot";
import { Button } from "@/components/ui/button";
import { content } from "@/components/marketing/content";

export function Hero() {
  return (
    <section className="hero-gradient relative overflow-hidden">
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-20 lg:grid-cols-2 lg:py-28">
        <div className="relative z-10 text-center lg:text-left">
          <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            {content.hero.eyebrow}
          </span>

          <h1 className="mt-5 text-4xl font-extrabold leading-[1.15] tracking-tight sm:text-5xl">
            {content.hero.title}{" "}
            <span className="text-primary">{content.hero.titleHighlight}</span>
          </h1>

          <p className="mx-auto mt-5 max-w-xl text-base text-muted-foreground sm:text-lg lg:mx-0">
            {content.hero.subtitle}
          </p>

          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row lg:justify-start">
            <Button asChild size="lg" className="w-full sm:w-auto">
              <Link href="/register">
                {content.hero.ctaPrimary}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
              <a href="#how-it-works">{content.hero.ctaSecondary}</a>
            </Button>
          </div>
        </div>

        <div className="relative z-10 flex items-center justify-center">
          <div className="pointer-events-none absolute h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
          <CapyMascot variant="greet" size="lg" width="clamp(220px, 26vw, 360px)" className="relative" />
        </div>
      </div>
    </section>
  );
}
