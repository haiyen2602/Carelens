const ADMIN_AUTH_KEY = "capymedi_admin_auth";

export function isAdminAuthed() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(ADMIN_AUTH_KEY) === "1";
}

export function setAdminAuthed(v: boolean) {
  if (v) window.localStorage.setItem(ADMIN_AUTH_KEY, "1");
  else window.localStorage.removeItem(ADMIN_AUTH_KEY);
}
