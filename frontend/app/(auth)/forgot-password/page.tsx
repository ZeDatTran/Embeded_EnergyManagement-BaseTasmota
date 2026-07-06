"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { forgotPassword, resetPassword } from "@/lib/auth-api";
import {
  Home,
  Zap,
  Eye,
  EyeOff,
  Mail,
  Loader2,
  Wifi,
  Shield,
  BarChart3,
  KeyRound,
  ArrowLeft,
  CheckCircle2,
} from "lucide-react";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (!email.trim()) {
      setError("Vui lòng nhập địa chỉ email");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await forgotPassword(email.trim().toLowerCase());
      setMessage(res.message || "Mã khôi phục đã được gửi tới email của bạn.");
      setStep(2);
    } catch (err: any) {
      setError(err.message || "Không thể gửi mã khôi phục mật khẩu");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (!code.trim() || !newPassword || !confirmPassword) {
      setError("Vui lòng điền đầy đủ thông tin");
      return;
    }

    if (newPassword.length < 6) {
      setError("Mật khẩu mới phải có ít nhất 6 ký tự");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await resetPassword({
        email: email.trim().toLowerCase(),
        code: code.trim(),
        new_password: newPassword,
      });
      setMessage(res.message || "Đặt lại mật khẩu thành công!");
      // Redirect to login after 3 seconds
      setTimeout(() => {
        router.push("/login");
      }, 3000);
    } catch (err: any) {
      setError(err.message || "Đặt lại mật khẩu thất bại");
    } finally {
      setIsSubmitting(false);
    }
  };

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
          <h1 className="auth-title">Khôi phục mật khẩu</h1>
          <p className="auth-subtitle">
            {step === 1
              ? "Nhập email của bạn để nhận mã khôi phục"
              : "Nhập mã khôi phục và thiết lập mật khẩu mới"}
          </p>
        </div>

        {/* Message Alert */}
        {message && (
          <div className="mb-4 p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-400 text-sm flex items-start gap-2 animate-in fade-in duration-200">
            <CheckCircle2 size={18} className="flex-shrink-0 mt-0.5" />
            <span>{message}</span>
          </div>
        )}

        {/* Step 1: Input Email */}
        {step === 1 && (
          <form onSubmit={handleSendCode} className="auth-form">
            <div className="auth-field">
              <label htmlFor="recovery-email" className="auth-label">
                Địa chỉ email
              </label>
              <div className="auth-input-wrapper">
                <input
                  id="recovery-email"
                  type="email"
                  placeholder="email@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="auth-input"
                  style={{ paddingRight: "40px" }}
                  disabled={isSubmitting}
                  required
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none">
                  <Mail size={18} />
                </div>
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
                  Đang gửi mã...
                </>
              ) : (
                <>
                  <KeyRound size={18} />
                  Gửi mã xác nhận
                </>
              )}
            </button>
          </form>
        )}

        {/* Step 2: Input Code & New Password */}
        {step === 2 && (
          <form onSubmit={handleResetPassword} className="auth-form">
            <div className="auth-field">
              <label htmlFor="recovery-code" className="auth-label">
                Mã xác nhận (OTP)
              </label>
              <input
                id="recovery-code"
                type="text"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="auth-input text-center tracking-[8px] font-mono text-lg"
                autoComplete="one-time-code"
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="auth-field">
              <label htmlFor="new-password" className="auth-label">
                Mật khẩu mới
              </label>
              <div className="auth-input-wrapper">
                <input
                  id="new-password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Ít nhất 6 ký tự"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="auth-input auth-input-pw"
                  autoComplete="new-password"
                  disabled={isSubmitting}
                  required
                />
                <button
                  type="button"
                  className="auth-pw-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="auth-field">
              <label htmlFor="confirm-password" className="auth-label">
                Xác nhận mật khẩu mới
              </label>
              <div className="auth-input-wrapper">
                <input
                  id="confirm-password"
                  type={showConfirm ? "text" : "password"}
                  placeholder="Nhập lại mật khẩu mới"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="auth-input auth-input-pw"
                  autoComplete="new-password"
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
                  Đang thiết lập lại...
                </>
              ) : (
                <>
                  <KeyRound size={18} />
                  Đặt lại mật khẩu
                </>
              )}
            </button>
          </form>
        )}

        {/* Footer */}
        <div className="auth-footer mt-6 flex justify-between items-center text-xs">
          <Link href="/login" className="flex items-center gap-1 text-gray-400 hover:text-white transition">
            <ArrowLeft size={14} /> Quay lại Đăng nhập
          </Link>
          {step === 2 && (
            <button
              type="button"
              onClick={() => setStep(1)}
              className="text-blue-400 hover:underline"
              disabled={isSubmitting}
            >
              Gửi lại mã
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
