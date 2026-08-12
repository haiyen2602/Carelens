"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function toISO(year: number, month: number, day: number) {
  return `${year}-${pad(month + 1)}-${pad(day)}`;
}

export function DoseMiniCalendar({
  isDoseDay,
  initialDate,
}: {
  isDoseDay: (iso: string) => boolean;
  initialDate?: string;
}) {
  const base = initialDate ? new Date(`${initialDate}T00:00:00Z`) : new Date();
  const [year, setYear] = useState(base.getUTCFullYear());
  const [month, setMonth] = useState(base.getUTCMonth());

  const startWeekday = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7;
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const now = new Date();
  const todayIso = toISO(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());

  const cells: (number | null)[] = [
    ...Array.from({ length: startWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const goPrev = () => {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
  };
  const goNext = () => {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
  };

  return (
    <div className="rounded-xl border border-border p-3">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={goPrev}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          aria-label="Tháng trước"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <p className="text-sm font-semibold">
          Tháng {month + 1}/{year}
        </p>
        <button
          type="button"
          onClick={goNext}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          aria-label="Tháng sau"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-7 text-center text-xs text-muted-foreground">
        {WEEKDAYS.map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>

      <div className="mt-1 grid grid-cols-7 gap-y-1 text-center text-sm">
        {cells.map((d, i) => {
          if (d === null) return <span key={`empty-${i}`} />;
          const iso = toISO(year, month, d);
          const hasDose = isDoseDay(iso);
          const isToday = iso === todayIso;
          return (
            <div key={iso} className="flex flex-col items-center gap-0.5 py-0.5">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full ${
                  isToday ? "bg-primary/10 font-semibold text-primary" : ""
                }`}
              >
                {d}
              </span>
              <span
                className={`h-1.5 w-1.5 rounded-full ${hasDose ? "bg-primary" : "bg-transparent"}`}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
