"use client";

import { useEffect, useState } from "react";

/**
 * Bong bong thoai cua mascot: go tung ky tu roi giu lai vai giay va go lai.
 * Dung setInterval thuan (khong GSAP) vi day la hieu ung text thuan tuy.
 */
export function MascotSpeech({ text, className }: { text: string; className?: string }) {
  const [shown, setShown] = useState("");
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setShown(text);
      return;
    }

    let i = 0;
    let holdTimer: ReturnType<typeof setTimeout> | undefined;

    const tick = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(tick);
        holdTimer = setTimeout(() => {
          setShown("");
          setCycle((c) => c + 1);
        }, 3200);
      }
    }, 40);

    return () => {
      clearInterval(tick);
      if (holdTimer) clearTimeout(holdTimer);
    };
    // cycle tang sau moi lan go xong -> effect chay lai, tao vong lap
  }, [text, cycle]);

  return (
    <div className={`relative ${className ?? ""}`}>
      <div className="relative rounded-[1.25rem] border border-border/70 bg-card px-4 py-2.5 shadow-[var(--shadow-card)]">
        {/* Ban sao an cua text de bong bong giu nguyen kich thuoc khi dang go */}
        <p aria-hidden className="invisible whitespace-nowrap text-sm font-medium">
          {text}
        </p>
        <p className="absolute inset-0 flex items-center whitespace-nowrap px-4 py-2.5 text-sm font-medium text-foreground">
          {shown}
        </p>
      </div>

      {/* Duoi bong bong kieu comic: hai chan tron nho dan, huong ve mascot */}
      <span className="absolute -bottom-2 left-1/2 h-4 w-4 -translate-x-8 rounded-full border border-border/70 bg-card" />
      <span className="absolute -bottom-5 left-1/2 h-2.5 w-2.5 -translate-x-12 rounded-full border border-border/70 bg-card" />
    </div>
  );
}
