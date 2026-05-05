import type React from "react"

export const metadata = {
  title: "Đăng nhập — Smart Home IoT",
  description: "Đăng nhập hoặc đăng ký tài khoản Smart Home",
}

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
