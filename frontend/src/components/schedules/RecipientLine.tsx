import { useEffect, useState } from "react";
import type { Api } from "../../api/client";
import type { RecipientPreview } from "../../api/types";

/** "Email goes to: …" for the chosen runbook, resolved by the server as a run would. */
export function RecipientLine({
  api,
  runbook,
  recipients,
}: {
  api: Api;
  runbook: string;
  recipients?: string[];
}) {
  const [preview, setPreview] = useState<RecipientPreview | null>(null);
  const key = recipients?.join(",") ?? "";

  useEffect(() => {
    if (!runbook) return;
    let active = true;
    const override = key ? key.split(",") : undefined;
    api.previewRecipients(runbook, override).then(
      (result) => active && setPreview(result),
      () => active && setPreview(null),
    );
    return () => {
      active = false;
    };
  }, [api, runbook, key]);

  let text = "Pick a runbook to see who gets the email.";
  if (runbook && preview) {
    text = preview.addresses.length
      ? `Email goes to: ${preview.addresses.join(", ")}`
      : "Nobody would get an email (no directory match and no default recipient).";
    if (preview.dropped > 0) text += ` (${preview.dropped} address(es) not in an allowed domain)`;
  }
  return (
    <p role="status" aria-label="Email recipients" className="text-sm text-slate-600">
      {text}
    </p>
  );
}
