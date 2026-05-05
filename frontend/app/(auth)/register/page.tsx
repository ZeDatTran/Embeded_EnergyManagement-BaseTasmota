"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import {
  Home,
  Zap,
  Eye,
  EyeOff,
  UserPlus,
  Loader2,
  Wifi,
  Shield,
  BarChart3,
  Check,
  X,
} from "lucide-react";

function getPasswordStrength(pw: string) {
  let score = 0;
  if (pw.length >= 6) score++;
  if (pw.length >= 10) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score; // 0-5
}

const strengthLabels = ["", "Yếu", "Yếu", "Trung bình", "Mạnh", "Rất mạnh"];
const strengthColors = [
  "",
  "var(--destructive)",
  "var(--destructive)",
  "var(--color-warning)",
  "var(--color-success)",
  "oklch(0.72 0.22 145)",
];

export default function RegisterPage() {
  const { register, isLoading: authLoading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const strength = useMemo(() => getPasswordStrength(password), [password]);
  const passwordsMatch = password === confirmPassword && confirmPassword !== "";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Client-side validation
    if (!email.trim() || !username.trim() || !password) {
      setError("Vui lòng nhập đầy đủ thông tin");
      return;
    }
    if (username.trim().length < 3) {
      setError("Tên đăng nhập phải có ít nhất 3 ký tự");
      return;
    }
    if (!/^[a-zA-Z0-9_]+$/.test(username.trim())) {
      setError("Tên đăng nhập chỉ chứa chữ cái, số và dấu gạch dưới");
      return;
    }
    if (password.length < 6) {
      setError("Mật khẩu phải có ít nhất 6 ký tự");
      return;
    }
    if (password !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp");
      return;
    }

    setIsSubmitting(true);
    try {
      await register({
        email: email.trim().toLowerCase(),
        username: username.trim(),
        password,
        full_name: fullName.trim(),
      });
    } catch (err: any) {
      setError(err.message || "Đăng ký thất bại");
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
      <div className="auth-card auth-card-register">
        {/* Logo & branding */}
        <div className="auth-brand">
          <div className="auth-logo">
            <Home size={28} />
            <Zap size={16} className="auth-logo-zap" />
          </div>
          <h1 className="auth-title">Tạo tài khoản</h1>
          <p className="auth-subtitle">Bắt đầu quản lý nhà thông minh</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="reg-fullname" className="auth-label">
              Họ và tên
            </label>
            <input
              id="reg-fullname"
              type="text"
              autoComplete="name"
              placeholder="Nguyễn Văn A"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="auth-input"
              disabled={isSubmitting}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="reg-email" className="auth-label">
              Email <span className="auth-required">*</span>
            </label>
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              placeholder="email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="auth-input"
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="auth-field">
            <label htmlFor="reg-username" className="auth-label">
              Tên đăng nhập <span className="auth-required">*</span>
            </label>
            <input
              id="reg-username"
              type="text"
              autoComplete="username"
              placeholder="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="auth-input"
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="auth-field">
            <label htmlFor="reg-password" className="auth-label">
              Mật khẩu <span className="auth-required">*</span>
            </label>
            <div className="auth-input-wrapper">
              <input
                id="reg-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Ít nhất 6 ký tự"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="auth-input auth-input-pw"
                disabled={isSubmitting}
                required
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
            {/* Password strength bar */}
            {password.length > 0 && (
              <div className="auth-strength">
                <div className="auth-strength-track">
                  <div
                    className="auth-strength-fill"
                    style={{
                      width: `${(strength / 5) * 100}%`,
                      background: strengthColors[strength],
                    }}
                  />
                </div>
                <span
                  className="auth-strength-label"
                  style={{ color: strengthColors[strength] }}
                >
                  {strengthLabels[strength]}
                </span>
              </div>
            )}
          </div>

          <div className="auth-field">
            <label htmlFor="reg-confirm" className="auth-label">
              Xác nhận mật khẩu <span className="auth-required">*</span>
            </label>
            <div className="auth-input-wrapper">
              <input
                id="reg-confirm"
                type={showConfirm ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Nhập lại mật khẩu"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="auth-input auth-input-pw"
                disabled={isSubmitting}
                required
              />
              <button
                type="button"
                className="auth-pw-toggle"
                onClick={() => setShowConfirm(!showConfirm)}
                tabIndex={-1}
              >
                {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {confirmPassword.length > 0 && (
              <div className="auth-match-hint">
                {passwordsMatch ? (
                  <span className="auth-match-ok">
                    <Check size={14} /> Mật khẩu khớp
                  </span>
                ) : (
                  <span className="auth-match-err">
                    <X size={14} /> Mật khẩu không khớp
                  </span>
                )}
              </div>
            )}
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
                Đang tạo tài khoản...
              </>
            ) : (
              <>
                <UserPlus size={18} />
                Đăng ký
              </>
            )}
          </button>
        </form>

        {/* Footer */}
        <p className="auth-footer">
          Đã có tài khoản?{" "}
          <Link href="/login" className="auth-link">
            Đăng nhập
          </Link>
        </p>
      </div>
    </div>
  );
}
