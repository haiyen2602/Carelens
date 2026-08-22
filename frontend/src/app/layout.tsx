import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "CapyMedi — Trợ lý nhắc uống thuốc có bác sĩ đồng hành",
  description:
    "CapyMedi giúp bệnh nhân uống đúng thuốc, đúng giờ, với bác sĩ theo sát mọi phác đồ và người thân luôn được cập nhật khi có bất thường.",
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-64.png", sizes: "64x64", type: "image/png" },
      { url: "/favicon-128.png", sizes: "128x128", type: "image/png" },
      { url: "/favicon.ico" },
    ],
    apple: "/apple-touch-icon.png",
  },
  // Bat buoc de iOS cho phep "Them vao Man hinh chinh" - dieu kien tien
  // quyet de Web Push chay duoc tren Safari (iOS >= 16.4). Android/desktop
  // khong can nhung co manifest thi cai duoc PWA cho gon.
  manifest: "/manifest.json",
  openGraph: { type: "website" },
  twitter: { card: "summary_large_image" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap"
        />
        {/* CapyMedi patient-portal rebrand fonts — scoped via .capymedi-theme in globals.css */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700;800&family=Be+Vietnam+Pro:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
