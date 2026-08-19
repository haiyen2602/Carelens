"use client";

import Image from "next/image";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";

export type MascotVariant = "idle" | "greet" | "celebrate";

const SIZES = { sm: 72, md: 120, lg: 180 } as const;

export function CapyMascot({
  variant = "idle",
  size = "md",
  className,
}: {
  variant?: MascotVariant;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const scope = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const body = scope.current?.querySelector(".capy-body");
      if (!body) return;

      gsap.set(body, { transformOrigin: "50% 90%", x: 0, y: 0, rotate: 0, scale: 1 });
      gsap.set(".capy-spark", { opacity: 0, scale: 0 });

      if (variant === "idle") {
        return gsap
          .timeline({ repeat: -1, yoyo: true, defaults: { ease: "sine.inOut" } })
          .to(body, { y: -6, scaleY: 1.03, scaleX: 0.98, duration: 1.4 });
      }

      if (variant === "greet") {
        const tl = gsap.timeline({ repeat: -1, repeatDelay: 2.5 });
        tl.to(body, { rotate: -7, duration: 0.22, ease: "power2.out" })
          .to(body, { rotate: 6, duration: 0.28, ease: "sine.inOut" })
          .to(body, { rotate: -5, duration: 0.28, ease: "sine.inOut" })
          .to(body, { rotate: 0, duration: 0.35, ease: "elastic.out(1, 0.45)" })
          .to(body, { y: -8, duration: 0.9, ease: "sine.inOut", yoyo: true, repeat: 1 });
        return tl;
      }

      const tl = gsap.timeline();
      tl.to(body, { scaleY: 0.82, scaleX: 1.12, duration: 0.16, ease: "power2.in" })
        .to(body, { y: -46, scaleY: 1.12, scaleX: 0.92, duration: 0.34, ease: "power2.out" })
        .to(body, { rotate: 12, duration: 0.34 }, "<")
        .to(body, { y: 0, scaleY: 0.9, scaleX: 1.08, duration: 0.28, ease: "power2.in" })
        .to(body, { rotate: 0, duration: 0.28 }, "<")
        .to(body, { scaleY: 1, scaleX: 1, duration: 0.7, ease: "elastic.out(1, 0.4)" })
        .to(
          ".capy-spark",
          {
            opacity: 1,
            scale: 1,
            duration: 0.3,
            stagger: { each: 0.05, from: "random" },
            ease: "back.out(2)",
          },
          0.35,
        )
        .to(".capy-spark", { opacity: 0, scale: 0.4, duration: 0.4, stagger: 0.04 }, "-=0.1");
      return tl;
    },
    { scope, dependencies: [variant] },
  );

  const px = SIZES[size];

  return (
    <div
      ref={scope}
      className={`pointer-events-none relative inline-block select-none ${className ?? ""}`}
      style={{ width: px, height: px * 1.07 }}
    >
      <div className="capy-body relative h-full w-full will-change-transform">
        <Image
          src="/mascot/capy-mascot.png"
          alt="CapyMedi mascot"
          fill
          sizes={`${px}px`}
          priority={size !== "sm"}
          className="object-contain"
        />
      </div>

      {variant === "celebrate" &&
        SPARKS.map((s, i) => (
          <span
            key={i}
            className="capy-spark absolute block rounded-full"
            style={{
              left: `${s.x}%`,
              top: `${s.y}%`,
              width: s.size,
              height: s.size,
              background: s.color,
            }}
          />
        ))}
    </div>
  );
}

const SPARKS = [
  { x: 8, y: 18, size: 8, color: "#e11d2f" },
  { x: 86, y: 12, size: 10, color: "#1a2b6b" },
  { x: 2, y: 52, size: 7, color: "#f5b301" },
  { x: 92, y: 46, size: 8, color: "#e11d2f" },
  { x: 18, y: 4, size: 6, color: "#1a2b6b" },
  { x: 70, y: 2, size: 9, color: "#f5b301" },
  { x: 96, y: 74, size: 6, color: "#1a2b6b" },
  { x: 4, y: 80, size: 9, color: "#e11d2f" },
];
