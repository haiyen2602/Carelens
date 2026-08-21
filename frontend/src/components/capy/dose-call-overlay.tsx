"use client";

// "Cuoc goi gia lap" - moc nhac thu 3 (+30 phut) khi benh nhan van chua xac
// nhan uong thuoc, sau 2 lan banner nhe (+0, +15 phut) khong an thua. KHONG
// phai cuoc goi that: khong quay so, khong ket noi gi ca - chi mo phong giao
// dien goi den de doi mot su chu y manh hon banner truot thong thuong.
//
// Am thanh o day KHONG dung playDoseAlarmShort()/playNudgeSound()
// (lib/notifications.ts) - 2 ham do phat 1 lan roi thoi. Chuong goi phai LAP
// LAI toi khi nguoi dung tu bam nut, nen tu quan ly the <audio> qua ref.

import Image from "next/image";
import { useEffect, useRef } from "react";

const CHU_KY_RUNG = [600, 300, 600, 300, 600, 300];

export function DoseCallOverlay({
  tenThuoc,
  gioHen,
  onClose,
}: {
  tenThuoc: string;
  gioHen: string;
  onClose: () => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const audio = new Audio("/sounds/alarm-call.wav");
    audio.loop = true;
    audioRef.current = audio;
    void audio.play().catch(() => {
      // Autoplay bi chan (tab chua tung co tuong tac) - overlay van hien
      // binh thuong, chi la khong co tieng.
    });

    // Vibration API: Android Chrome/Firefox co, iOS Safari KHONG (Apple chua
    // bao gio trien khai, ke ca Chrome tren iOS vi dung chung WebKit) - guard
    // de khong nem loi tren may khong ho tro, im lang bo qua.
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate(CHU_KY_RUNG);
    }

    return () => {
      audio.pause();
      audioRef.current = null;
      if (typeof navigator !== "undefined" && "vibrate" in navigator) {
        navigator.vibrate(0); // huy rung con lai trong hang doi
      }
    };
  }, []);

  return (
    <div className="absolute inset-0 z-[58] flex flex-col items-center justify-between overflow-hidden bg-[#16386E] px-8 py-12 text-center text-white">
      <Image
        src="/capy_nhacnho.png"
        alt=""
        fill
        sizes="430px"
        className="pointer-events-none object-cover opacity-25"
        priority
      />

      <div className="relative flex flex-col items-center gap-2">
        <p className="font-mono m-0 text-[12px] uppercase tracking-[0.18em] text-white/70">
          Cuộc gọi nhắc thuốc
        </p>
        <p className="font-display m-0 text-[26px] font-extrabold leading-[1.2]">CapyMedi</p>
        <p className="m-0 text-[14px] text-white/80">đang gọi bạn…</p>
      </div>

      <div className="relative flex flex-col items-center gap-3">
        <span className="grid h-[132px] w-[132px] place-items-center overflow-hidden rounded-full bg-white/15 ring-4 ring-white/25">
          <Image src="/capy_nhacnho.png" alt="" width={132} height={132} className="object-cover" />
        </span>
        <p className="font-display m-0 text-[20px] font-bold leading-[1.3]">{tenThuoc}</p>
        <p className="m-0 text-[14px] text-white/80">Hẹn lúc {gioHen} — bạn uống chưa?</p>
      </div>

      <div className="relative flex w-full items-center justify-center gap-6">
        <button
          onClick={onClose}
          className="flex flex-col items-center gap-2"
          aria-label="Từ chối cuộc gọi"
        >
          <span className="grid h-[66px] w-[66px] place-items-center rounded-full bg-[#E23B33] text-[26px] transition-transform hover:scale-105">
            ✕
          </span>
          <span className="text-[12.5px] font-semibold text-white/85">Từ chối</span>
        </button>
        <button
          onClick={onClose}
          className="flex flex-col items-center gap-2"
          aria-label="Trả lời cuộc gọi"
        >
          <span className="grid h-[66px] w-[66px] place-items-center rounded-full bg-[#2E9E6B] text-[26px] transition-transform hover:scale-105">
            📞
          </span>
          <span className="text-[12.5px] font-semibold text-white/85">Trả lời</span>
        </button>
      </div>
    </div>
  );
}
