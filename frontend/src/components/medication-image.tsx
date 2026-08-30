"use client";

import { useEffect, useState } from "react";
import { ImageOff, Loader2, Pill } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { MedicationImage as MedicationImageData } from "@/lib/doses";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type MedicationImageProps = {
  image: MedicationImageData;
  accessToken: string | null | undefined;
  drugName: string;
  size?: "sm" | "md";
};

const SIZE = {
  sm: "h-11 w-11 rounded-xl",
  md: "h-20 w-20 rounded-2xl",
} as const;

function Placeholder({ size, label }: { size: "sm" | "md"; label: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className={`${SIZE[size]} flex shrink-0 items-center justify-center bg-[#EDF1F7] text-[#62708A]`}
    >
      <Pill className={size === "sm" ? "h-4 w-4" : "h-7 w-7"} aria-hidden="true" />
    </div>
  );
}

/** Fetch an authorized catalog image as a short-lived browser Blob URL. */
export function MedicationImage({
  image,
  accessToken,
  drugName,
  size = "sm",
}: MedicationImageProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(image.status === "AVAILABLE");
  const [failed, setFailed] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    setPreviewOpen(false);
    setObjectUrl(null);
    if (image.status !== "AVAILABLE" || !image.url || !accessToken) {
      setLoading(false);
      setFailed(image.status === "AVAILABLE");
      return;
    }
    const controller = new AbortController();
    let url: string | null = null;
    setLoading(true);
    setFailed(false);
    fetch(`${BACKEND_URL}${image.url}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Medication image request failed: ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setObjectUrl(url);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setFailed(true);
      })
      .finally(() => setLoading(false));
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [accessToken, image.status, image.url]);

  if (image.status !== "AVAILABLE")
    return <Placeholder size={size} label="Chưa có hình ảnh thuốc" />;
  if (loading) {
    return (
      <div
        className={`${SIZE[size]} flex shrink-0 items-center justify-center bg-[#EDF1F7] text-[#62708A]`}
        aria-label="Đang tải hình ảnh thuốc"
      >
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      </div>
    );
  }
  if (failed || !objectUrl) {
    return (
      <div
        className={`${SIZE[size]} flex shrink-0 items-center justify-center bg-[#EDF1F7] text-[#62708A]`}
        role="img"
        aria-label="Không tải được hình ảnh thuốc"
      >
        <ImageOff className={size === "sm" ? "h-4 w-4" : "h-7 w-7"} aria-hidden="true" />
      </div>
    );
  }
  return (
    <>
      <button
        type="button"
        aria-label={`Xem ảnh thuốc ${drugName}`}
        onClick={() => setPreviewOpen(true)}
        className={`${SIZE[size]} shrink-0 overflow-hidden bg-white focus:outline-none focus:ring-2 focus:ring-[#16386E] focus:ring-offset-2`}
      >
        <img
          src={objectUrl}
          alt={image.alt || `Hình ảnh bao bì ${drugName}`}
          width={size === "sm" ? 44 : 80}
          height={size === "sm" ? 44 : 80}
          className="h-full w-full object-contain p-1"
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      </button>
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-2xl border-[#E3E8F1] bg-white p-5">
          <DialogHeader className="pr-8">
            <DialogTitle className="text-[#16386E]">Ảnh thuốc: {drugName}</DialogTitle>
            <DialogDescription>Ảnh bao bì thuốc đã được xác thực cho đơn của bạn.</DialogDescription>
          </DialogHeader>
          <img
            src={objectUrl}
            alt={image.alt || `Hình ảnh bao bì ${drugName}`}
            className="max-h-[70vh] w-full rounded-xl bg-[#F4F7FC] object-contain"
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
