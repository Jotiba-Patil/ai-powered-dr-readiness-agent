import { useId } from "react";
import type { Cadence } from "../../api/types";
import { WEEKDAYS } from "../../lib/scheduleLabels";
import { FIELD } from "./fieldStyles";

const INPUT = FIELD;

const MONTH_DAYS = Array.from({ length: 31 }, (_, index) => index + 1);

/** Preset cadence: hourly at a minute, daily at a time, weekly or monthly on a day at a time. */
export function CadenceFields({
  cadence,
  onChange,
}: {
  cadence: Cadence;
  onChange: (cadence: Cadence) => void;
}) {
  const kindId = useId();
  const valueId = useId();
  const dayId = useId();
  const monthDayId = useId();
  const time = cadence.kind === "hourly" ? "06:00" : cadence.time;
  const setKind = (kind: Cadence["kind"]) => {
    if (kind === "hourly") onChange({ kind, minute: 0 });
    else if (kind === "daily") onChange({ kind, time });
    else if (kind === "monthly") onChange({ kind, day: 1, time });
    else onChange({ kind, weekday: "mon", time });
  };
  return (
    <div className="flex flex-wrap gap-3">
      <label htmlFor={kindId} className="text-sm">
        <span className="block font-medium text-slate-700">Repeat</span>
        <select
          id={kindId}
          value={cadence.kind}
          onChange={(event) => setKind(event.target.value as Cadence["kind"])}
          className={INPUT}
        >
          <option value="hourly">Hourly</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </label>
      {cadence.kind === "monthly" && (
        <label htmlFor={monthDayId} className="text-sm">
          <span className="block font-medium text-slate-700">Day of month</span>
          <select
            id={monthDayId}
            value={String(cadence.day)}
            onChange={(event) => {
              const value = event.target.value;
              onChange({ ...cadence, day: value === "last" ? "last" : Number(value) });
            }}
            className={INPUT}
          >
            {MONTH_DAYS.map((day) => (
              <option key={day} value={day}>
                {day > 28 ? `${day} (or the last day)` : day}
              </option>
            ))}
            <option value="last">Last day of the month</option>
          </select>
        </label>
      )}
      {cadence.kind === "weekly" && (
        <label htmlFor={dayId} className="text-sm">
          <span className="block font-medium text-slate-700">Day</span>
          <select
            id={dayId}
            value={cadence.weekday}
            onChange={(event) =>
              onChange({ ...cadence, weekday: event.target.value as (typeof WEEKDAYS)[number] })
            }
            className={INPUT}
          >
            {WEEKDAYS.map((day) => (
              <option key={day} value={day}>
                {day.charAt(0).toUpperCase() + day.slice(1)}
              </option>
            ))}
          </select>
        </label>
      )}
      {cadence.kind === "hourly" ? (
        <label htmlFor={valueId} className="text-sm">
          <span className="block font-medium text-slate-700">Minute past the hour</span>
          <input
            id={valueId}
            type="number"
            min={0}
            max={59}
            value={cadence.minute}
            onChange={(event) => onChange({ kind: "hourly", minute: Number(event.target.value) })}
            className={`${INPUT} w-20`}
          />
        </label>
      ) : (
        <label htmlFor={valueId} className="text-sm">
          <span className="block font-medium text-slate-700">Time</span>
          <input
            id={valueId}
            type="time"
            value={cadence.time}
            required
            onChange={(event) => onChange({ ...cadence, time: event.target.value })}
            className={INPUT}
          />
        </label>
      )}
    </div>
  );
}
