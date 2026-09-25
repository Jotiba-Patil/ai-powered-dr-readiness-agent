import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ExecutionPhase, RtoAnalysis } from "../api/types";
import { waterfall } from "../lib/waterfall";
import { minutes } from "../lib/labels";
import { Section } from "./Section";

export function RtoTimeline({ rto, phases }: { rto: RtoAnalysis; phases: ExecutionPhase[] }) {
  const rows = phases.length > 0 ? waterfall(phases, rto.totalEstimatedMinutes) : [];
  const bottlenecks = rto.bottleneckSteps ?? [];
  const over = rto.bufferMinutes < 0;
  const end = Math.max(rto.statedRtoMinutes, ...rows.map((r) => r.start + r.duration));
  return (
    <Section title="RTO feasibility">
      <p className={over ? "font-semibold text-red-700" : "font-semibold text-emerald-700"}>
        <span aria-hidden="true">{rto.feasible ? "✔ " : "✖ "}</span>
        {rto.feasible ? "Feasible" : "Not feasible"}: estimated {minutes(rto.totalEstimatedMinutes)}{" "}
        against a stated RTO of {minutes(rto.statedRtoMinutes)}
      </p>
      <p className="text-sm text-slate-600">
        {over
          ? `Over the RTO by ${minutes(-rto.bufferMinutes)}.`
          : `Buffer: ${minutes(rto.bufferMinutes)}.`}
        {bottlenecks.length > 0 && ` Bottleneck steps: ${bottlenecks.join(", ")}.`}
      </p>
      {rows.length > 0 && (
        <div
          className="mt-3"
          style={{ height: 60 + rows.length * 40 }}
          role="img"
          aria-label="Execution phases timeline against the RTO"
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            initialDimension={{ width: 600, height: 60 + rows.length * 40 }}
          >
            <BarChart data={rows} layout="vertical" margin={{ top: 18, left: 8, right: 24 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[0, Math.ceil(end * 1.1)]} unit=" min" />
              <YAxis type="category" dataKey="name" width={70} />
              <Tooltip formatter={(value) => minutes(Number(value))} />
              <Bar
                dataKey="start"
                stackId="t"
                fill="transparent"
                name="Starts at"
                isAnimationActive={false}
              />
              <Bar
                dataKey="duration"
                stackId="t"
                name="Duration"
                maxBarSize={28}
                isAnimationActive={false}
              >
                {rows.map((row) => (
                  <Cell key={row.name} fill={row.total ? "#94a3b8" : "#0891b2"} />
                ))}
              </Bar>
              <ReferenceLine
                x={rto.statedRtoMinutes}
                stroke="#dc2626"
                strokeDasharray="4 4"
                label={{ value: "RTO", position: "top", fill: "#dc2626" }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {rows.length > 0 && (
        <p className="mt-1 text-xs text-slate-500">
          Phase bars show wall-clock time (steps in a phase run in parallel). Total is the sum of
          all step estimates, which the RTO check uses. Dashed line: stated RTO.
        </p>
      )}
    </Section>
  );
}
