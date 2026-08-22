import { Capabilities } from "@/components/marketing/capabilities";
import { Hero } from "@/components/marketing/hero";
import { HowItWorks } from "@/components/marketing/how-it-works";
import { Safety } from "@/components/marketing/safety";
import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { Trust } from "@/components/marketing/trust";

// Landing page (giai doan 1-2 cua redesign, xem HANDOFF/product-vision.md
// muc 2.1). Login da doi sang /login (giai doan 2). Section la server
// component mac dinh - chi CapyMascot/MascotSpeech ben trong Hero la client
// component (can GSAP/useRef).
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background">
      <SiteHeader />
      <Hero />
      <Capabilities />
      <HowItWorks />
      <Safety />
      <Trust />
      <SiteFooter />
    </main>
  );
}
