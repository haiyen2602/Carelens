import Link from "next/link";
import Image from "next/image";

import { content } from "@/components/marketing/content";

export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border/60 bg-background">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-10 sm:grid-cols-[1.5fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <Image
                src="/logo-capymedi-v2.png"
                alt="CapyMedi"
                width={28}
                height={28}
                className="h-7 w-7"
              />
              <span className="font-extrabold tracking-tight">{content.header.logo}</span>
            </div>
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">{content.footer.note}</p>
          </div>

          <div>
            <h3 className="text-sm font-semibold">{content.footer.product.title}</h3>
            <ul className="mt-3 space-y-2">
              {content.footer.product.links.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-sm font-semibold">{content.footer.account.title}</h3>
            <ul className="mt-3 space-y-2">
              {content.footer.account.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="mt-10 border-t border-border/60 pt-6 text-xs text-muted-foreground">
          {content.footer.copyright(year)}
        </p>
      </div>
    </footer>
  );
}
