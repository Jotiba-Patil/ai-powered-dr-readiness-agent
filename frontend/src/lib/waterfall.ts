import type { ExecutionPhase } from "../api/types";

export interface Row {
  name: string;
  start: number;
  duration: number;
  total: boolean;
}

/**
 * Waterfall rows: each phase starts where the previous one ended (parallel steps share a phase),
 * followed by the sequential total of all step estimates, which is what the RTO check uses.
 */
export function waterfall(phases: ExecutionPhase[], totalMinutes: number): Row[] {
  let offset = 0;
  const rows = phases.map((phase) => {
    const row = {
      name: `Phase ${phase.phase}`,
      start: offset,
      duration: phase.estimatedMinutes,
      total: false,
    };
    offset += phase.estimatedMinutes;
    return row;
  });
  return [...rows, { name: "Total", start: 0, duration: totalMinutes, total: true }];
}
