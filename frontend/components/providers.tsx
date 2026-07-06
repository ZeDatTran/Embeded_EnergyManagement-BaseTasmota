"use client"

import type { ReactNode } from "react"
import { QueryClientProvider, QueryClient } from "@tanstack/react-query"
import { SocketProvider } from "@/context/SocketContext"
import { AuthProvider } from "@/context/AuthContext"
import { ThemeProvider } from "./theme-provider"

// Create a client
const queryClient = new QueryClient()

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <AuthProvider>
          <SocketProvider>{children}</SocketProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
