"use client";

import { useState } from "react";

interface GroupSetupModalProps {
  onSave: (groupId: string) => Promise<void>;
  onSkip?: () => void;
}

export function GroupSetupModal({ onSave, onSkip }: GroupSetupModalProps) {
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = groupId.trim();
    if (!trimmed) {
      setError("Vui lòng nhập Group Device ID");
      return;
    }
    // Basic UUID format check
    const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRe.test(trimmed)) {
      setError("Group ID không đúng định dạng UUID (ví dụ: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await onSave(trimmed);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-md mx-4 rounded-2xl border border-white/10 bg-gray-900 shadow-2xl p-8">
        {/* Icon */}
        <div className="flex justify-center mb-5">
          <div className="w-14 h-14 rounded-full bg-blue-500/20 flex items-center justify-center">
            <svg className="w-7 h-7 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5" />
            </svg>
          </div>
        </div>

        <h2 className="text-xl font-semibold text-white text-center mb-1">
          Kết nối CoreIoT
        </h2>
        <p className="text-sm text-gray-400 text-center mb-6">
          Nhập <span className="text-blue-400 font-medium">Group Device ID</span> từ tài khoản CoreIoT của bạn để bắt đầu giám sát thiết bị.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5" htmlFor="group-id-input">
              Group Device ID
            </label>
            <input
              id="group-id-input"
              type="text"
              value={groupId}
              onChange={(e) => { setGroupId(e.target.value); setError(""); }}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition font-mono"
              disabled={loading}
              autoFocus
            />
            {error && (
              <p className="mt-1.5 text-xs text-red-400">{error}</p>
            )}
          </div>

          <div className="pt-1 text-xs text-gray-500 bg-white/5 rounded-lg px-3 py-2.5">
            <span className="text-gray-400 font-medium">Tìm Group ID ở đâu?</span>
            <br />
            Đăng nhập CoreIoT → <span className="text-gray-300">Entity Groups</span> → chọn nhóm thiết bị → copy ID trong URL
          </div>

          <div className="flex gap-3 pt-2">
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                disabled={loading}
                className="flex-1 py-2.5 rounded-lg border border-white/10 text-gray-400 text-sm hover:bg-white/5 transition disabled:opacity-50"
              >
                Bỏ qua
              </button>
            )}
            <button
              type="submit"
              disabled={loading || !groupId.trim()}
              className="flex-1 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Đang lưu...
                </>
              ) : "Kết nối"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
