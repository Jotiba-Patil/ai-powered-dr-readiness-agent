import { useCallback, useState } from "react";

const KEY = "dr-agent.approver-name";

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * The person's name, remembered in this browser only as a convenience. It is not an identity:
 * the server records whatever name is sent (the UI says so next to the field).
 */
export function useStoredName(): [string, (name: string) => void] {
  const [name, setName] = useState(read);
  const update = useCallback((next: string) => {
    setName(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // storage can be unavailable (private mode, blocked site data); the name still works
    }
  }, []);
  return [name, update];
}
