import { isApiError } from "@/lib/api";
import { errorText } from "../auth/messages";
import type { ShowToast } from "./Toast";

// What an admin tab does when an action fails: a signed-out (or deactivated) admin goes back to the
// sign-in card; any other error is shown as a toast.
export function handleFailure(err: unknown, toast: ShowToast, onSignedOut: () => void): void {
  if (isApiError(err) && err.code === "UNAUTHENTICATED") onSignedOut();
  else toast(errorText(err), true);
}
