import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-outfit",
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "YT Recent Videos",
  description: "Liệt kê video YouTube 2 ngày gần nhất từ kênh theo dõi — OAuth, tải về, upload, sửa mô tả.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={outfit.variable}>
      <body className="font-sans text-ink antialiased min-h-[100dvh] bg-paper">
        {children}
      </body>
    </html>
  );
}
