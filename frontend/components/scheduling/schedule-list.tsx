"use client"

import { useSchedules, useDeleteSchedule, useToggleSchedule } from "@/hooks/use-schedules"
import { useUIStore } from "@/lib/store"
import { Trash2, Edit2, Clock, Calendar, Zap, ZapOff } from "lucide-react"

export function ScheduleList() {
  const { data: schedules, isLoading, error } = useSchedules()
  const { mutate: deleteSchedule } = useDeleteSchedule()
  const { mutate: toggleSchedule } = useToggleSchedule()
  const { setScheduleEditorOpen } = useUIStore()

  const handleEdit = (schedule: any) => {
    setScheduleEditorOpen(true, schedule.id)
  }

  const handleDelete = (id: string) => {
    if (confirm("Bạn có chắc muốn xóa lịch này không?")) {
      deleteSchedule(id)
    }
  }

  const handleToggleEnabled = (scheduleId: string) => {
    toggleSchedule(scheduleId)
  }

  // ── Loading / Error / Empty states ──────────────────────────────────
  if (isLoading) {
    return (
      <div className="overflow-hidden rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
        Đang tải lịch...
      </div>
    )
  }

  if (error) {
    return (
      <div className="overflow-hidden rounded-lg border border-border bg-card p-8 text-center text-red-500">
        Lỗi tải lịch. Vui lòng kiểm tra server đang chạy.
      </div>
    )
  }

  if (!schedules || schedules.length === 0) {
    return (
      <div className="overflow-hidden rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
        Chưa có lịch nào được tạo
      </div>
    )
  }

  return (
    <>
      {/* ── Mobile: card layout (hidden on sm+) ─────────────────────── */}
      <div className="flex flex-col gap-3 sm:hidden">
        {schedules.map((schedule) => (
          <div
            key={schedule.id}
            className="rounded-lg border border-border bg-card p-4 shadow-sm space-y-3"
          >
            {/* Row 1: name + toggle + action buttons */}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-semibold text-foreground">{schedule.name}</p>
                <p className="truncate text-xs text-muted-foreground mt-0.5">{schedule.targetId}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => handleEdit(schedule)}
                  className="rounded-md p-2 text-blue-600 transition-colors hover:bg-blue-50 dark:hover:bg-blue-900/40"
                  aria-label="Chỉnh sửa"
                >
                  <Edit2 size={16} />
                </button>
                <button
                  onClick={() => handleDelete(schedule.id)}
                  className="rounded-md p-2 text-red-600 transition-colors hover:bg-red-50 dark:hover:bg-red-900/40"
                  aria-label="Xóa"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>

            {/* Row 2: badges */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Action badge */}
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  schedule.action === "on"
                    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                    : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                }`}
              >
                {schedule.action === "on" ? <Zap size={11} /> : <ZapOff size={11} />}
                {schedule.action === "on" ? "Bật" : "Tắt"}
              </span>

              {/* Type badge */}
              <span
                className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  schedule.runOnce
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100"
                    : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100"
                }`}
              >
                {schedule.runOnce ? "Một lần" : "Lặp lại"}
              </span>

              {/* Enabled toggle */}
              <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground select-none">
                <input
                  type="checkbox"
                  checked={schedule.enabled}
                  onChange={() => handleToggleEnabled(schedule.id)}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
                Bật
              </label>
            </div>

            {/* Row 3: time + days */}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {schedule.time}
              </span>
              <span className="flex items-center gap-1">
                <Calendar size={12} />
                {schedule.days.join(", ")}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* ── Desktop: table layout (hidden on mobile) ─────────────────── */}
      <div className="hidden sm:block overflow-hidden rounded-lg border border-border bg-card text-card-foreground">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Tên</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Thiết bị</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Loại</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Hành động</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Giờ</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Ngày</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Bật</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((schedule) => (
                <tr key={schedule.id} className="border-b border-border transition-colors hover:bg-muted/40">
                  <td className="px-6 py-4 text-sm font-medium text-foreground">{schedule.name}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground max-w-[160px] truncate">{schedule.targetId}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      schedule.runOnce
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100"
                        : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100"
                    }`}>
                      {schedule.runOnce ? "Một lần" : "Lặp lại"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      schedule.action === "on"
                        ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                    }`}>
                      {schedule.action === "on" ? "Bật" : "Tắt"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-foreground">{schedule.time}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{schedule.days.join(", ")}</td>
                  <td className="px-6 py-4 text-sm">
                    <input
                      type="checkbox"
                      checked={schedule.enabled}
                      onChange={() => handleToggleEnabled(schedule.id)}
                      className="h-4 w-4 rounded border-border accent-primary"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <div className="flex gap-1">
                      <button
                        onClick={() => handleEdit(schedule)}
                        className="rounded p-1.5 text-blue-600 transition-colors hover:bg-blue-50 dark:hover:bg-blue-900/40"
                        aria-label="Chỉnh sửa"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => handleDelete(schedule.id)}
                        className="rounded p-1.5 text-red-600 transition-colors hover:bg-red-50 dark:hover:bg-red-900/40"
                        aria-label="Xóa"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
