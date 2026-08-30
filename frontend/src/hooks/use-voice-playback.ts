"use client";

// Phat audio TTS - moi lan la 1 Blob moi (khac frontend/src/lib/notifications.ts's
// playNudgeSound()/playDoseAlarmShort(), von phat file tinh /sounds/*.wav lap lai).
//
// VI SAO PHAI CO moKhoa(): trinh duyet chi cho phat tieng khi lenh play() xuat
// phat tu mot cu cham THAT cua nguoi dung. Luong o day thi khong: nguoi dung
// cham nut gui -> doi Agent V2 tra loi (vai giay) -> doi TTS dung am (vai giay
// nua) -> luc do moi play(). Toi thoi diem do "quyen" tu cu cham da het han,
// nen Safari tren iPhone (ngat nhat trong cac trinh duyet) chan thang.
//
// Cach lam duoc: MOT the <audio> duy nhat, "mo khoa" no ngay trong handler cua
// cu cham (phat mot file WAV im lang 45 byte), roi cac lan sau chi doi .src cua
// CHINH the do - the da duoc nguoi dung kich hoat thi phat lai bang code duoc
// phep. Truoc day moi luot lai `new Audio(...)`: the moi tinh chua tung duoc
// cham vao nen luon bi chan.

import { useEffect, useRef } from "react";

// WAV im lang 45 byte (8kHz, mono, 8-bit, 1 mau). Dung de "mo khoa" the audio
// ma nguoi dung khong nghe thay gi.
const AM_THANH_IM_LANG =
  "data:audio/wav;base64,UklGRiUAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQEAAACA";

export function useVoicePlayback() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const daMoKhoa = useRef(false);

  const layThe = (): HTMLAudioElement => {
    if (!audioRef.current) audioRef.current = new Audio();
    return audioRef.current;
  };

  /** PHAI goi DONG BO trong handler cua cu cham that (nut gui / nut dung ghi
   *  am). Goi trong callback bat dong bo sau do thi vo tac dung - luc ay
   *  quyen tu cu cham da het. Goi nhieu lan khong sao, chi chay lan dau. */
  const moKhoa = () => {
    if (daMoKhoa.current) return;
    const audio = layThe();
    audio.src = AM_THANH_IM_LANG;
    const p = audio.play();
    if (p) {
      p.then(() => {
        audio.pause();
        audio.currentTime = 0;
        daMoKhoa.current = true;
      }).catch(() => {
        // Khong mo khoa duoc (vd goi ngoai cu cham) - khong phai loi can bao,
        // play() ben duoi se tu bao neu that su bi chan.
      });
    }
  };

  const play = (blob: Blob): Promise<void> => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    const url = URL.createObjectURL(blob);
    urlRef.current = url;
    // DUNG LAI the cu, khong tao the moi - day chinh la thu giu duoc "quyen"
    // ma nguoi dung da cap luc cham nut.
    const audio = layThe();
    audio.pause();
    audio.src = url;
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

  return { play, stop, moKhoa };
}
