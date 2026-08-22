import Link from "next/link";
import Image from "next/image";

import { Button } from "@/components/ui/button";
import { content } from "@/components/marketing/content";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={32}
            height={32}
            className="h-8 w-8"
            priority
          />
          <span className="text-lg font-extrabold tracking-tight">{content.header.logo}</span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {content.header.nav.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">{content.header.login}</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/register">{content.header.cta}</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
