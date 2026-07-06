"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import {
  Home,
  Zap,
  Eye,
  EyeOff,
  LogIn,
  Loader2,
  Wifi,
  Shield,
  BarChart3,
} from "lucide-react";

export default function LoginPage() {
  const { login, isLoading: authLoading } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!identifier.trim() || !password) {
      setError("Vui lòng nhập đầy đủ thông tin");
      return;
    }
    setIsSubmitting(true);
    try {
      await login(identifier.trim(), password);
    } catch (err: any) {
      setError(err.message || "Đăng nhập thất bại");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="auth-page">
        <div className="auth-bg" />
        <div className="auth-loading">
          <Loader2 className="auth-loading-icon" />
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      {/* Animated gradient background */}
      <div className="auth-bg" />

      {/* Floating decorative elements */}
      <div className="auth-float auth-float-1"><Wifi size={24} /></div>
      <div className="auth-float auth-float-2"><Shield size={20} /></div>
      <div className="auth-float auth-float-3"><BarChart3 size={22} /></div>
      <div className="auth-float auth-float-4"><Zap size={18} /></div>

      {/* Glass card */}
      <div className="auth-card">
        {/* Logo & branding */}
        <div className="auth-brand">
          <div className="auth-logo">
            <Home size={28} />
            <Zap size={16} className="auth-logo-zap" />
          </div>
          <h1 className="auth-title">Smart Home</h1>
          <p className="auth-subtitle">Quản lý nhà thông minh</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="login-identifier" className="auth-label">
              Email hoặc tên đăng nhập
            </label>
            <input
              id="login-identifier"
              type="text"
              autoComplete="username"
              placeholder="email@example.com"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="auth-input"
              disabled={isSubmitting}
            />
          </div>

          <div className="auth-field">
            <div className="flex justify-between items-center mb-1">
              <label htmlFor="login-password" className="auth-label" style={{ marginBottom: 0 }}>
                Mật khẩu
              </label>
              <Link href="/forgot-password" className="text-xs text-blue-400 hover:text-blue-300 transition">
                Quên mật khẩu?
              </Link>
            </div>
            <div className="auth-input-wrapper">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="auth-input auth-input-pw"
                disabled={isSubmitting}
              />
              <button
                type="button"
                className="auth-pw-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="auth-btn"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={18} className="auth-btn-spin" />
                Đang đăng nhập...
              </>
            ) : (
              <>
                <LogIn size={18} />
                Đăng nhập
              </>
            )}
          </button>
        </form>

        {/* Footer */}
        <p className="auth-footer">
          Chưa có tài khoản?{" "}
          <Link href="/register" className="auth-link">
            Đăng ký ngay
          </Link>
        </p>
      </div>
    </div>
  );
}
