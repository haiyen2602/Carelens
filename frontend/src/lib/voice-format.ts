// Chon dinh dang ghi am va suy ra ten file gui len OpenAI.
//
// Tach rieng khoi use-voice-recorder.ts (von import React) de test duoc bang
// node --experimental-strip-types, giong cach lib/voice-settings.ts tach
// phan luu tuy chon ra khoi component.

// Thu tu UU TIEN khi chon dinh dang ghi am. KHONG duoc chi thu moi
// "audio/webm" roi bo trong: Safari tren iPhone khong ho tro webm, no se tu
// chon MP4 va ta khong biet no da chon gi de dat ten file cho dung.
export const UU_TIEN_MIME = ["audio/webm", "audio/mp4", "audio/ogg"];

// OpenAI doc dinh dang theo DUOI TEN FILE chu khong theo noi dung: do thuc
// te bang MOT file mp3 duy nhat - gui ten "voice.mp3" nhan dung, gui ten
// "voice.webm" tra ve "Audio file might be corrupted or unsupported".
// Vi vay duoi PHAI khop dinh dang that, khong duoc hard-code.
const DUOI_THEO_MIME: Record<string, string> = {
  "audio/webm": "webm",
  "audio/mp4": "mp4",
  "audio/ogg": "ogg",
  "audio/mpeg": "mp3",
  "audio/wav": "wav",
  "audio/x-wav": "wav",
};

export function tenFileGhiAm(mimeType: string | undefined | null): string {
  // mimeType thuong kem codec ("audio/webm;codecs=opus") - chi lay phan mime.
  const mime = (mimeType || "").split(";")[0].trim().toLowerCase();
  const duoi = DUOI_THEO_MIME[mime];
  // Khong nhan ra mime -> gui KHONG duoi. Do thuc te: OpenAI tu do noi dung
  // va van nhan dung khi ten file khong co duoi, con doan bua mot duoi sai
  // thi hong chac chan.
  return duoi ? `voice.${duoi}` : "voice";
}
