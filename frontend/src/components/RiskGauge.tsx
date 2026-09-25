import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";
import type { RiskLevel } from "../api/types";
import { RISK_TONES } from "../lib/labels";
import { Badge } from "./Badge";

/** Half-circle 0-100 risk gauge; the score and level are also plain text. */
export function RiskGauge({ score, level }: { score: number; level: RiskLevel }) {
  const tone = RISK_TONES[level];
  return (
    <figure className="flex flex-col items-center" aria-label={`Risk score ${score} of 100`}>
      <div className="relative h-32 w-56" aria-hidden="true">
        <RadialBarChart
          width={224}
          height={224}
          cx={112}
          cy={112}
          innerRadius={80}
          outerRadius={108}
          startAngle={180}
          endAngle={0}
          data={[{ value: score, fill: tone.color }]}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" background cornerRadius={6} isAnimationActive={false} />
        </RadialBarChart>
      </div>
      <figcaption className="-mt-14 text-center">
        <p className="text-4xl font-bold">
          {score}
          <span className="text-base font-normal text-slate-500">/100</span>
        </p>
        <p className="mt-1">
          <Badge tone={tone} text={`${tone.label} risk`} />
        </p>
      </figcaption>
    </figure>
  );
}
