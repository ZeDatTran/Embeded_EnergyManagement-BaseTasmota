"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { sendVerificationCode, verifyEmail } from "@/lib/auth-api";

function InfoRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 py-3 border-b border-white/5 last:border-0">
      <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`text-sm text-gray-200 break-all ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      title="Sao chép"
      className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200 transition"
    >
      {copied ? (
        <>
          <svg className="w-3 h-3 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          Đã sao chép
        </>
      ) : (
        <>
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Copy
        </>
      )}
    </button>
  );
}

export default function ProfilePage() {
  const { user, token, logout, openGroupSetup, refreshUser } = useAuth();

  // Verification modal states
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [sendingOtp, setSendingOtp] = useState(false);
  const [verifyError, setVerifyError] = useState("");
  const [verifySuccess, setVerifySuccess] = useState("");

  const handleStartVerification = async () => {
    if (!token) return;
    setVerifyError("");
    setVerifySuccess("");
    setSendingOtp(true);
    setShowVerifyModal(true);
    try {
      await sendVerificationCode(token);
      setVerifySuccess("Mã OTP xác thực đã được gửi tới email của bạn!");
    } catch (err: any) {
      setVerifyError(err.message || "Không thể gửi mã xác thực. Vui lòng thử lại.");
    } finally {
      setSendingOtp(false);
    }
  };

  const handleSendOtpAgain = async () => {
    if (!token) return;
    setVerifyError("");
    setVerifySuccess("");
    setSendingOtp(true);
    try {
      await sendVerificationCode(token);
      setVerifySuccess("Mã OTP mới đã được gửi tới email của bạn!");
    } catch (err: any) {
      setVerifyError(err.message || "Không thể gửi mã xác thực. Vui lòng thử lại.");
    } finally {
      setSendingOtp(false);
    }
  };

  const handleSubmitVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !otpCode.trim()) return;
    setVerifyError("");
    setVerifySuccess("");
    setVerifying(true);
    try {
      await verifyEmail(token, otpCode.trim());
      setVerifySuccess("Xác thực email thành công!");
      await refreshUser();
      setTimeout(() => {
        setShowVerifyModal(false);
        setOtpCode("");
        setVerifySuccess("");
      }, 1500);
    } catch (err: any) {
      setVerifyError(err.message || "Mã xác thực không chính xác hoặc đã hết hạn.");
    } finally {
      setVerifying(false);
    }
  };

  if (!user) return null;

  const initials = (user.full_name || user.username).substring(0, 2).toUpperCase();
  const joinedDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })
    : "—";

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="mx-auto max-w-2xl space-y-6">

        {/* Page Title */}
        <div>
          <h1 className="text-2xl font-bold text-white">Hồ sơ cá nhân</h1>
          <p className="text-sm text-gray-500 mt-0.5">Quản lý thông tin tài khoản và kết nối CoreIoT</p>
        </div>

        {/* Avatar + basic info */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-blue-600 flex items-center justify-center text-2xl font-bold text-white flex-shrink-0">
              {initials}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{user.full_name || user.username}</h2>
              <p className="text-sm text-gray-400">{user.email}</p>
              <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-300 capitalize">
                {user.role}
              </span>
            </div>
          </div>
        </div>

        {/* Account info */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Thông tin tài khoản</h3>
          <div>
            <InfoRow label="Tên đăng nhập" value={user.username} />
            <InfoRow label="Họ và tên" value={user.full_name || <span className="text-gray-600 italic">Chưa cập nhật</span>} />
            <InfoRow 
              label="Email" 
              value={
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <span>{user.email}</span>
                  <div className="flex items-center gap-2">
                    {user.email_verified ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/15 text-green-400">
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        Đã xác thực
                      </span>
                    ) : (
                      <>
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-500/15 text-red-400">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                          Chưa xác thực
                        </span>
                        <button
                          onClick={handleStartVerification}
                          className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition"
                        >
                          Xác thực ngay
                        </button>
                      </>
                    )}
                  </div>
                </div>
              } 
            />
            <InfoRow label="Ngày tham gia" value={joinedDate} />
          </div>
        </div>

        {/* CoreIoT Connection */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-300">Kết nối CoreIoT</h3>
              <p className="text-xs text-gray-500 mt-0.5">Group Device ID xác định nhóm thiết bị của bạn</p>
            </div>
            {/* Status badge */}
            <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${user.group_id ? "bg-green-500/15 text-green-400" : "bg-yellow-500/15 text-yellow-400"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${user.group_id ? "bg-green-400" : "bg-yellow-400"}`} />
              {user.group_id ? "Đã kết nối" : "Chưa kết nối"}
            </span>
          </div>

          {user.group_id ? (
            <div className="bg-white/5 rounded-xl p-4 mb-4">
              <p className="text-xs text-gray-500 mb-1">Group Device ID</p>
              <div className="flex items-center gap-2">
                <code className="text-sm text-blue-300 font-mono break-all">{user.group_id}</code>
                <CopyButton text={user.group_id} />
              </div>
            </div>
          ) : (
            <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4 mb-4">
              <p className="text-sm text-yellow-400">
                Chưa kết nối với nhóm thiết bị nào. Nhập Group ID để bắt đầu giám sát thiết bị.
              </p>
            </div>
          )}

          <button
            id="change-group-id-btn"
            onClick={openGroupSetup}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            {user.group_id ? "Thay đổi Group ID" : "Kết nối CoreIoT"}
          </button>
        </div>

        {/* Danger zone */}
        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-6">
          <h3 className="text-sm font-semibold text-red-400 mb-1">Vùng nguy hiểm</h3>
          <p className="text-xs text-gray-500 mb-4">Đăng xuất khỏi tài khoản trên thiết bị này.</p>
          <button
            id="logout-btn"
            onClick={logout}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-500/30 text-red-400 hover:bg-red-500/10 text-sm font-medium transition"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Đăng xuất
          </button>
        </div>

      </div>

      {/* Email Verification Modal */}
      {showVerifyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-slate-900/95 p-6 shadow-2xl backdrop-blur-md animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">Xác thực tài khoản Email</h3>
              <p className="text-xs text-gray-400 mt-1">Mã OTP 6 chữ số đã được gửi đến email: <span className="text-gray-200 font-medium">{user.email}</span></p>
            </div>

            {/* Notifications */}
            {verifySuccess && (
              <div className="mb-4 p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-400 text-xs">
                {verifySuccess}
              </div>
            )}
            {verifyError && (
              <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                {verifyError}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmitVerification} className="space-y-4">
              <div>
                <label htmlFor="otp-input" className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">
                  Mã xác thực (OTP)
                </label>
                <input
                  id="otp-input"
                  type="text"
                  maxLength={6}
                  placeholder="123456"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-center tracking-[8px] font-mono text-lg text-white focus:border-blue-500 focus:outline-none transition"
                  autoComplete="one-time-code"
                  disabled={verifying}
                  required
                  autoFocus
                />
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Chưa nhận được mã?</span>
                <button
                  type="button"
                  onClick={handleSendOtpAgain}
                  className="text-blue-400 hover:text-blue-300 font-medium transition disabled:opacity-50"
                  disabled={sendingOtp || verifying}
                >
                  {sendingOtp ? "Đang gửi lại..." : "Gửi lại mã OTP"}
                </button>
              </div>

              {/* Actions */}
              <div className="flex gap-3 justify-end pt-2 border-t border-white/5">
                <button
                  type="button"
                  onClick={() => {
                    setShowVerifyModal(false);
                    setVerifyError("");
                    setVerifySuccess("");
                    setOtpCode("");
                  }}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white text-sm font-medium transition"
                  disabled={verifying}
                >
                  Hủy bỏ
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition disabled:opacity-50"
                  disabled={verifying || !otpCode.trim() || sendingOtp}
                >
                  {verifying ? (
                    <>
                      <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Đang xác minh...
                    </>
                  ) : (
                    "Xác nhận"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
