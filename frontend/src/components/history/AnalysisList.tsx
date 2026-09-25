import { useId, useState } from "react";
import type { AnalysisSummary, RiskLevel } from "../../api/types";
import type { HistoryFilters } from "../../hooks/useHistory";
import { RISK_TONES, utcMinute } from "../../lib/labels";
import { Badge } from "../Badge";

const RISK_LEVELS: RiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

interface Props {
  items: AnalysisSummary[];
  filters: HistoryFilters;
  onFilters: (filters: HistoryFilters) => void;
  hasMore: boolean;
  onMore: () => void;
  onOpen: (analysisId: string) => void;
}

/** Filters plus a table of stored analyses; presentational (data comes from `useHistory`). */
export function AnalysisList({ items, filters, onFilters, hasMore, onMore, onOpen }: Props) {
  const serviceId = useId();
  const riskId = useId();
  const [service, setService] = useState(filters.service);
  return (
    <div className="space-y-3">
      <form
        role="search"
        aria-label="Filter stored analyses"
        onSubmit={(event) => {
          event.preventDefault();
          onFilters({ ...filters, service });
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <div className="flex flex-col">
          <label htmlFor={serviceId} className="text-sm font-medium">
            Service
          </label>
          <input
            id={serviceId}
            value={service}
            placeholder="Exact service name"
            onChange={(event) => setService(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 shadow-sm"
          />
        </div>
        <div className="flex flex-col">
          <label htmlFor={riskId} className="text-sm font-medium">
            Risk level
          </label>
          <select
            id={riskId}
            value={filters.riskLevel}
            onChange={(event) =>
              onFilters({ ...filters, riskLevel: event.target.value as RiskLevel | "" })
            }
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 shadow-sm"
          >
            <option value="">Any</option>
            {RISK_LEVELS.map((level) => (
              <option key={level} value={level}>
                {RISK_TONES[level].label}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn-primary py-1.5 text-sm">
          Apply
        </button>
      </form>
      {items.length === 0 ? (
        <p role="status" className="text-sm text-slate-600">
          No stored analyses match. Finished analyses are stored automatically.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-3 py-2 font-semibold">Analyzed</th>
                <th className="px-3 font-semibold">Service</th>
                <th className="px-3 font-semibold">Risk</th>
                <th className="px-3 font-semibold">RTO</th>
                <th className="px-3 font-semibold">Runs</th>
                <th className="px-3">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className="border-t border-slate-100 transition hover:bg-signal-500/5"
                >
                  <td className="tabular px-3 py-2.5 text-slate-600">
                    {utcMinute(item.completedAt)}
                  </td>
                  <td className="px-3">
                    <span className="font-medium text-ink-900">{item.serviceName}</span>
                    <span className="block text-xs text-slate-500">{item.runbookLabel}</span>
                  </td>
                  <td className="px-3">
                    <Badge
                      tone={RISK_TONES[item.riskLevel]}
                      text={`${item.riskScore} ${RISK_TONES[item.riskLevel].label}`}
                    />
                  </td>
                  <td
                    className={`px-3 ${item.rtoFeasible ? "text-emerald-800" : "font-medium text-red-800"}`}
                  >
                    {item.rtoFeasible ? "Feasible" : "Not feasible"}
                  </td>
                  <td className="px-3">
                    <span className="tabular rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                      {item.executionCount}
                    </span>
                  </td>
                  <td className="px-3 text-right">
                    <button
                      type="button"
                      onClick={() => onOpen(item.id)}
                      className="btn-ghost py-1 text-xs"
                      aria-label={`Open ${item.serviceName} analysis from ${utcMinute(item.completedAt)}`}
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {hasMore && (
        <button type="button" onClick={onMore} className="btn-ghost">
          Load more
        </button>
      )}
    </div>
  );
}
