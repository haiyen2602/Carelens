"use client";

import { Check } from "lucide-react";

import { CapyMascot } from "@/components/mascot/capy-mascot";
import { MascotSpeech } from "@/components/mascot/mascot-speech";

const BENEFITS = ["Nhắc thuốc đúng giờ", "Theo dõi tuân thủ", "Người nhà an tâm"];

export function HeroPanel() {
  return (
    <aside className="auth-hero relative hidden items-center justify-center overflow-hidden lg:flex">
      <div className="relative flex w-[min(100%,820px)] -translate-y-10 flex-col items-center px-10 py-10">
        {/* Quang sang mem phia sau mascot - dinh vi theo hero container, khong
            phai theo viewport (tranh vo khi doi tu 1366px sang 1920px). */}
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-[clamp(320px,32vw,520px)] w-[clamp(320px,32vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/[0.07] blur-3xl" />

        <MascotSpeech
          text="Uống thuốc đúng giờ, người nhà bớt lo 💙"
          className="relative z-10 max-w-[min(100%,26rem)]"
        />

        <CapyMascot
          variant="idle"
          size="lg"
          width="clamp(226px, 20.6vw, 376px)"
          className="relative z-10 mt-10"
        />

        {/* O desktop chieu cao thap (1280x720, 1366x768) an benefits truoc,
            mascot van duoc giu lai. */}
        <ul className="relative z-10 mt-8 flex flex-col gap-3 [@media(max-height:780px)]:hidden">
          {BENEFITS.map((b) => (
            <li key={b} className="flex items-center gap-2.5 text-sm text-foreground/80">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                <Check className="h-3 w-3" strokeWidth={3} />
              </span>
              {b}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
