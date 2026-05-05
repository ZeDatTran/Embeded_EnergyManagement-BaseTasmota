"use client"

import type React from "react"

import { useState, useEffect } from "react"
import { useCreateSchedule, useUpdateSchedule, useSchedules } from "@/hooks/use-schedules"
import { useDeviceTree } from "@/hooks/use-devices"
import { useUIStore } from "@/lib/store"
import { X } from "lucide-react"

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

export function ScheduleEditor() {
  const { isScheduleEditorOpen, editingScheduleId, setScheduleEditorOpen } = useUIStore()
  const { data: schedules } = useSchedules()
  const { data: tree } = useDeviceTree()
  const { mutate: createSchedule } = useCreateSchedule()
  const { mutate: updateSchedule } = useUpdateSchedule()

  const [formData, setFormData] = useState({
    name: "",
    targetId: "",
    action: "on" as "on" | "off",
    time: "12:00",
    days: [] as string[],
    enabled: true,
    runOnce: false,
  })

  // Load schedule data if editing
  useEffect(() => {
    if (editingScheduleId && schedules) {
      const schedule = schedules.find((s) => s.id === editingScheduleId)
      if (schedule) {
        setFormData({
          name: schedule.name,
          targetId: schedule.targetId,
          action: schedule.action,
          time: schedule.time,
          days: schedule.days,
          enabled: schedule.enabled,
          runOnce: !!schedule.runOnce,
        })
      }
    } else {
      setFormData({
        name: "",
        targetId: "",
        action: "on",
        time: "12:00",
        days: [],
        enabled: true,
        runOnce: false,
      })
    }
  }, [editingScheduleId, schedules])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name || !formData.targetId || formData.days.length === 0) {
      alert("Please fill in all required fields")
      return
    }

    if (formData.runOnce && formData.days.length !== 1) {
      alert("One-time schedule requires selecting exactly 1 day")
      return
    }

    if (editingScheduleId) {
      updateSchedule({
        id: editingScheduleId,
        ...formData,
      } as any)
    } else {
      createSchedule(formData)
    }

    setScheduleEditorOpen(false)
  }

  const toggleDay = (day: string) => {
    if (formData.runOnce) {
      setFormData((prev) => ({
        ...prev,
        days: prev.days.includes(day) ? [] : [day],
      }))
      return
    }

    setFormData((prev) => ({
      ...prev,
      days: prev.days.includes(day) ? prev.days.filter((d) => d !== day) : [...prev.days, day],
    }))
  }

  if (!isScheduleEditorOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4">
      {/* Modal: full-screen bottom sheet on mobile, centered dialog on sm+ */}
      <div className="max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl border border-border bg-card text-card-foreground shadow-xl sm:max-h-[90vh] sm:max-w-md sm:rounded-lg">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card px-4 py-4 sm:px-6">
          {/* Drag handle (mobile only) */}
          <div className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-muted-foreground/30 sm:hidden" />
          <h2 className="text-base font-semibold sm:text-lg">
            {editingScheduleId ? "Chỉnh sửa lịch" : "Tạo lịch mới"}
          </h2>
          <button
            onClick={() => setScheduleEditorOpen(false)}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-4 py-5 sm:px-6">
          {/* Schedule name */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Tên lịch <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="VD: Bật đèn buổi tối"
            />
          </div>

          {/* Target device */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Thiết bị / Nhóm <span className="text-red-500">*</span>
            </label>
            <select
              value={formData.targetId}
              onChange={(e) => setFormData({ ...formData, targetId: e.target.value })}
              className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Chọn thiết bị hoặc nhóm</option>
              {tree?.map((area: any) => (
                <optgroup key={area.id} label={area.name}>
                  {area.children?.map((group: any) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {/* Action + Time (side by side on all screens) */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Hành động <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.action}
                onChange={(e) => setFormData({ ...formData, action: e.target.value as "on" | "off" })}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="on">Bật</option>
                <option value="off">Tắt</option>
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Giờ <span className="text-red-500">*</span>
              </label>
              <input
                type="time"
                value={formData.time}
                onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          {/* Run-once toggle */}
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-3 select-none">
            <input
              type="checkbox"
              id="run-once"
              checked={formData.runOnce}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  runOnce: e.target.checked,
                  days: e.target.checked ? formData.days.slice(0, 1) : formData.days,
                })
              }
              className="h-4 w-4 shrink-0 rounded border-border accent-primary"
            />
            <span className="text-sm text-foreground leading-tight">
              Chạy một lần rồi tự xóa sau khi thực thi
            </span>
          </label>

          {/* Days of week */}
          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">
              Ngày trong tuần <span className="text-red-500">*</span>
              {formData.runOnce && (
                <span className="ml-1 text-xs font-normal text-muted-foreground">(chọn đúng 1 ngày)</span>
              )}
            </label>
            {/* 7 buttons in a single row — wrap naturally on tiny screens */}
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((day) => {
                const selected = formData.days.includes(day)
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => toggleDay(day)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${selected
                        ? "bg-primary text-primary-foreground"
                        : "border border-border bg-background text-muted-foreground hover:bg-accent"
                      }`}
                  >
                    {day}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Enabled */}
          <label className="flex cursor-pointer items-center gap-3 select-none">
            <input
              type="checkbox"
              id="enabled"
              checked={formData.enabled}
              onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              className="h-4 w-4 rounded border-border accent-primary"
            />
            <span className="text-sm text-muted-foreground">Kích hoạt lịch này ngay</span>
          </label>

          {/* Buttons */}
          <div className="flex gap-3 pt-2 pb-1">
            <button
              type="button"
              onClick={() => setScheduleEditorOpen(false)}
              className="flex-1 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              Hủy
            </button>
            <button
              type="submit"
              className="flex-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              {editingScheduleId ? "Cập nhật" : "Tạo lịch"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
