/** What a schedule change is doing now, or why the last one failed. */
export function ActionNotice({ pending, error }: { pending: string | null; error: string | null }) {
  return (
    <>
      {pending && (
        <p role="status" className="flex items-center gap-2 text-sm text-signal-700">
          <span
            aria-hidden="true"
            className="h-3 w-3 animate-spin rounded-full border-2 border-signal-500 border-t-transparent motion-reduce:animate-none"
          />
          {pending}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-xl bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200"
        >
          {error}
        </p>
      )}
    </>
  );
}
