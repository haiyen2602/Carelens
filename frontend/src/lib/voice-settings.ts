// Tuy chon "tro ly co the noi" - CHI luu localStorage (khong persist backend),
// khop hanh vi da so switch trong account-settings.tsx (chi photo_capture_enabled
// moi that su goi PATCH /patients/me vi no doi hanh vi xac nhan lieu thuoc,
// day la tuy chon hien thi thuan tuy, khong co y nghia lam sang/da thiet bi).

const VOICE_OUTPUT_KEY = "capymedi_patient_voice_output_enabled";

export function loadVoiceOutputEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(VOICE_OUTPUT_KEY) === "1";
}

export function saveVoiceOutputEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(VOICE_OUTPUT_KEY, enabled ? "1" : "0");
}
