import type React from "react"
import { Header } from "./header"
import { ChatWidget } from "../chatbot/ChatWidget"

interface MainLayoutProps {
  children: React.ReactNode
}

export function MainLayout({ children }: MainLayoutProps) {
  return (
    <div className="relative min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 container py-6 px-4 md:py-8">{children}</main>
      <ChatWidget />
    </div>
  )
}
