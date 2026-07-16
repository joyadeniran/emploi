import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "Emploi — Your Career Twin",
  description:
    "Your Career Twin finds opportunities, verifies employers, and prepares your best applications. Starting in Africa, built for the world.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${jakarta.variable} h-full antialiased`}>
      {/* suppressHydrationWarning: browser extensions inject attributes into
          <body> before hydration (e.g. bis_register), tripping a false
          mismatch. Applies to this element's attributes only. */}
      <body className="min-h-full" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
