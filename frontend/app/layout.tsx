import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Content Calendar", description: "Editorial workspace for your X content engine" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
