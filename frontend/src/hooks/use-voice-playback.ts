"use client";

// Phat audio TTS - moi lan la 1 Blob moi (khac frontend/src/lib/notifications.ts's
// playNudgeSound()/playDoseAlarmShort(), von phat file tinh /sounds/*.wav lap
// lai). Mau HTMLAudioElement + .play().catch(()=>{}) (nuot loi autoplay-block)
// giu nguyen tu dose-call-overlay.tsx/notifications.ts; them revoke Object URL
// cu truoc khi tao moi de khong ri bo nhớ qua nhieu luot.

import { useEffect, useRef } from "react";

export function useVoicePlayback() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  // Tra ve Promise thay vi nuot loi: truoc day `.catch(() => {})` lam moi
  // that bai deu IM LANG - trinh duyet chan autoplay thi nguoi dung ngoi doi
  // mot cau tra loi khong bao gio phat ra tieng va khong hieu vi sao. Nguoi
  // goi (assistant/page.tsx) tu quyet dinh hien thong bao gi.
  const play = (blob: Blob): Promise<void> => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    audioRef.current?.pause();
    const url = URL.createObjectURL(blob);
    urlRef.current = url;
    const audio = new Audio(url);
    audioRef.current = audio;
    return audio.play();
  };

  const stop = () => {
    audioRef.current?.pause();
  };

  useEffect(
    () => () => {
      audioRef.current?.pause();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    [],
  );

  return { play, stop };
}
