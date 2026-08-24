import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "CoolProof — Urban cooling decisions",
    template: "%s · CoolProof",
  },
  description: "Understand urban heat, compare cooling investments, and verify what changed.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
