import type { ScheduleView } from "../../api/types";
import { Icon } from "../ui/Icon";
import type { ScheduleActions } from "./ScheduleList";

const ACTION = "btn-ghost inline-flex items-center gap-1.5 px-2.5 py-1";

/** Run now, pause or resume, delete; each names its schedule for screen readers. */
export function RowActions({
  schedule,
  actions,
  canAct,
  onPause,
}: {
  schedule: ScheduleView;
  actions: ScheduleActions;
  canAct: boolean;
  onPause: () => void;
}) {
  const { id, name } = schedule;
  return (
    <div className="flex justify-end gap-1 whitespace-nowrap">
      <button
        type="button"
        className={`${ACTION} border-signal-500/40 text-signal-700`}
        disabled={!canAct}
        aria-label={`Run ${name} now`}
        title="Analyze now and email the result"
        onClick={() => actions.runNow(id)}
      >
        <Icon name="play" className="h-3.5 w-3.5" />
        Run now
      </button>
      {schedule.enabled ? (
        <button
          type="button"
          className={ACTION}
          disabled={!canAct}
          aria-label={`Pause ${name}`}
          onClick={onPause}
        >
          <Icon name="pause" className="h-3.5 w-3.5" />
          Pause…
        </button>
      ) : (
        <button
          type="button"
          className={`${ACTION} text-emerald-800`}
          disabled={!canAct}
          aria-label={`Resume ${name}`}
          onClick={() => actions.resume(id)}
        >
          <Icon name="play" className="h-3.5 w-3.5" />
          Resume
        </button>
      )}
      <button
        type="button"
        className={`${ACTION} text-red-700 hover:!bg-red-50`}
        disabled={!canAct}
        aria-label={`Delete ${name}`}
        title="Delete (its analyses stay in History)"
        onClick={() => actions.remove(id)}
      >
        <Icon name="trash" className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
