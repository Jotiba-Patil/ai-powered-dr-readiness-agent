import type { Tone } from "../lib/labels";

/** A colored pill that always shows an icon plus text, so color is never the only signal. */
export function Badge({ tone, text }: { tone: Tone; text?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${tone.className}`}
    >
      <span aria-hidden="true">{tone.icon}</span>
      {text ?? tone.label}
    </span>
  );
}
