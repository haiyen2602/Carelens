export const DEFAULT_TIMES: Record<number, string[]> = {
  1: ["08:00"],
  2: ["08:00", "20:00"],
  3: ["08:00", "13:00", "20:00"],
  4: ["07:00", "12:00", "17:00", "21:00"],
};

export function today() {
  return new Date().toISOString().slice(0, 10);
}

export type DoseSchedule = {
  startDate: string;
  endDate: string;
  hasCycle: boolean;
  cycleOnDays: number;
  cycleOffDays: number;
};

export function appliesOnDate(schedule: DoseSchedule, iso: string) {
  if (!schedule.startDate || iso < schedule.startDate) return false;
  if (schedule.endDate && iso > schedule.endDate) return false;
  if (!schedule.hasCycle) return true;
  const cycleLen = schedule.cycleOnDays + schedule.cycleOffDays;
  if (cycleLen <= 0) return true;
  const diffDays = Math.round(
    (new Date(`${iso}T00:00:00Z`).getTime() -
      new Date(`${schedule.startDate}T00:00:00Z`).getTime()) /
      86_400_000,
  );
  const pos = ((diffDays % cycleLen) + cycleLen) % cycleLen;
  return pos < schedule.cycleOnDays;
}

export function shiftTime(hhmm: string, minutes: number) {
  const [h, m] = hhmm.split(":").map(Number);
  const total = ((h ?? 0) * 60 + (m ?? 0) + minutes + 1440) % 1440;
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
