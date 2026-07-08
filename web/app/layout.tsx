import type { Metadata, Viewport } from "next"
import { Geist_Mono, Inter } from "next/font/google"
import "./globals.css"

// Inter carries the Raycast typographic voice (ss03 stylistic set, enabled
// globally in globals.css). Geist Mono stays for path/code chips.
const inter = Inter({ variable: "--font-inter", subsets: ["latin"] })
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "OMYM2 Console",
  description:
    "Local control console for OMYM2 — review configuration, runs, consistency checks, and managed tracks. File operations run through the CLI.",
  icons: {
    icon: [
      {
        url: "/icon-light-32x32.png",
        media: "(prefers-color-scheme: light)",
      },
      {
        url: "/icon-dark-32x32.png",
        media: "(prefers-color-scheme: dark)",
      },
      {
        url: "/icon.svg",
        type: "image/svg+xml",
      },
    ],
    apple: "/apple-icon.png",
  },
}

export const viewport: Viewport = {
  // This console is dark-only — the Raycast system has no light mode, so the
  // browser chrome (scrollbars, form controls) should render dark too.
  colorScheme: "dark",
  themeColor: "#07080a",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} bg-background`}
      style={{ scrollbarGutter: "stable" }}
    >
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
