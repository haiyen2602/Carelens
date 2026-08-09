"use client";

const days = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const slots = ["07:00", "12:00", "19:00", "21:00"];
const data = [
  [92, 88, 95, 71, 84, 66, 60],
  [90, 94, 87, 78, 80, 72, 64],
  [86, 82, 90, 68, 76, 70, 58],
  [74, 70, 66, 62, 68, 55, 50],
];

export default function HeatmapPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Heatmap theo cữ uống</h1>
        <p className="text-sm text-muted-foreground">Tỷ lệ uống đúng khung an toàn ±30 phút.</p>
      </header>
      <div className="surface-card overflow-x-auto p-6">
        <table className="min-w-[520px] border-separate border-spacing-1">
          <thead>
            <tr>
              <th />
              {days.map((d) => (
                <th key={d} className="px-2 pb-2 text-xs font-semibold text-muted-foreground">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slots.map((s, r) => (
              <tr key={s}>
                <td className="pr-3 text-xs font-semibold text-muted-foreground">{s}</td>
                {days.map((d, c) => {
                  const v = data[r]?.[c] ?? 0;
                  return (
                    <td key={d}>
                      <div
                        className="grid h-11 w-14 place-items-center rounded-lg text-xs font-bold text-primary"
                        style={{
                          background: `color-mix(in oklab, var(--primary) ${v / 2}%, transparent)`,
                        }}
                      >
                        {v}%
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
