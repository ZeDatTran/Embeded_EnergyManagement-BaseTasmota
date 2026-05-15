"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";

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
  const { user, logout, openGroupSetup } = useAuth();

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
            <InfoRow label="Email" value={user.email} />
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
    </div>
  );
}
