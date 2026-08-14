"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function moTaLoi(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError") {
    return "Trình duyệt chưa được cấp quyền camera. Hãy cho phép truy cập camera rồi thử lại.";
  }
  if (name === "NotFoundError") {
    return "Không tìm thấy camera trên thiết bị này.";
  }
  return "Không mở được camera.";
}

// May co the cai webcam ao (Camo Studio, OBS Virtual Camera, Snap Camera,
// DroidCam...) - getUserMedia({video: true}) don gian de trinh duyet tu
// chon thiet bi mac dinh, co the roi dung vao webcam ao thay vi camera vat
// ly that. Nhan dien va tranh cac ten hay gap, chi lay deviceId that.
const WEBCAM_AO = /camo|obs|virtual|snap camera|manycam|droidcam|iriun|epoccam|elgato/i;

async function layDeviceIdCameraThat(): Promise<string | undefined> {
  // Nhan dang thiet bi (label) chi co sau khi da xin quyen it nhat 1 lan -
  // xin quyen tam bang constraint chung chung, dung ngay stream do, roi
  // enumerate lai de doc label that.
  const tam = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  tam.getTracks().forEach((t) => t.stop());

  const thietBi = await navigator.mediaDevices.enumerateDevices();
  const camera = thietBi.filter((d) => d.kind === "videoinput");
  const camThat = camera.find((d) => !WEBCAM_AO.test(d.label));
  return (camThat ?? camera[0])?.deviceId;
}

export function CameraCapture({
  open,
  onOpenChange,
  onCapture,
  onFallbackToFile,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCapture: (file: File) => void;
  // getUserMedia can bi chan (quyen, khong co camera, trinh duyet khong ho
  // tro) - thay vi ket thuc bit tac, cho nguoi dung mot loi thoat sang chon
  // file thu cong.
  onFallbackToFile: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [dangMo, setDangMo] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoi(null);
    setDangMo(true);
    let huy = false;

    layDeviceIdCameraThat()
      .then((deviceId) =>
        navigator.mediaDevices.getUserMedia({
          video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "environment" },
          audio: false,
        }),
      )
      .then((stream) => {
        if (huy) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setDangMo(false);
      })
      .catch((err) => {
        if (huy) return;
        setDangMo(false);
        setLoi(moTaLoi(err));
      });

    return () => {
      huy = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open]);

  const chup = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        onCapture(new File([blob], `dose-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.9,
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Chụp ảnh xác nhận</DialogTitle>
          <DialogDescription>Bày thuốc ra trước camera rồi bấm chụp.</DialogDescription>
        </DialogHeader>

        <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`h-full w-full object-cover ${dangMo || loi ? "invisible" : ""}`}
          />
          {dangMo && (
            <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white">
              <Loader2 className="h-4 w-4 animate-spin" /> Đang mở camera…
            </div>
          )}
          {loi && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-sm text-white">
              <p>{loi}</p>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          {loi ? (
            <Button
              className="w-full"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                onFallbackToFile();
              }}
            >
              <Upload className="mr-1 h-4 w-4" /> Tải ảnh lên thay thế
            </Button>
          ) : (
            <Button className="w-full" size="lg" disabled={dangMo} onClick={chup}>
              <Camera className="mr-1 h-4 w-4" /> Chụp
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
