import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import styles from "./layout.module.css";
import { Sidebar } from "./Sidebar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "GhostKube Console",
  description: "Operator console for GhostKube",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <div className={styles.shell}>
          <Sidebar />
          <main className={styles.content}>
            <div className={styles.contentInner}>{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
