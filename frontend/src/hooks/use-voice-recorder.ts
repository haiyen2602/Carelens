"use client";

// Ghi am giong noi qua MediaRecorder - hoan toan moi trong codebase nay
// (chua co MediaRecorder/getUserMedia audio o dau khac). Xu ly quyen theo
// dung mau frontend/src/components/camera-capture.tsx::moTaLoi(), don gian
// hon vi audio khong can enumerateDevices/chon thiet bi nhu camera.

import { useEffect, useRef, useState } from "react";

import { UU_TIEN_MIME } from "@/lib/voice-format";

export type VoiceRecorderState = "idle" | "recording";

function moTaLoiMic(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError") {
    return "Trình duyệt chưa được cấp quyền micro. Hãy cho phép truy cập micro rồi thử lại.";
  }
  if (name === "NotFoundError") {
    return "Không tìm thấy micro trên thiết bị này.";
  }
  return "Không mở được micro.";
}

export function useVoiceRecorder() {
  const [state, setState] = useState<VoiceRecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const start = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = UU_TIEN_MIME.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setState("recording");
    } catch (err) {
      setError(moTaLoiMic(err));
    }
  };

  const stop = (): Promise<Blob | null> =>
    new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setState("idle");
        resolve(chunksRef.current.length ? new Blob(chunksRef.current, { type: recorder.mimeType }) : null);
      };
      recorder.stop();
    });

  // Nha micro khi component bi go bo GIUA CHUNG ghi am. Viec tat track chi
  // nam trong onstop o tren, ma onstop chi chay khi nguoi dung TU bam dung -
  // nen roi trang luc dang ghi (thanh dieu huong o capy-shell.tsx luon hien,
  // chi can bam sang tab khac) se de stream song tiep: den "dang ghi am" cua
  // trinh duyet van sang du nguoi dung tuong da thoat. Cung tinh than cleanup
  // nhu use-voice-playback.ts, von da co san.
  useEffect(
    () => () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        // Go handler TRUOC khi stop: no goi setState tren component da
        // unmount va resolve mot promise khong con ai doi.
        recorder.onstop = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    },
    [],
  );

  return { state, error, start, stop };
}
