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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg border border-border bg-card text-card-foreground shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-6">
          <h2 className="text-lg font-semibold">{editingScheduleId ? "Edit Schedule" : "Create Schedule"}</h2>
          <button
            onClick={() => setScheduleEditorOpen(false)}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Schedule Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="e.g., Evening Lights"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Target Device/Group *</label>
            <select
              value={formData.targetId}
              onChange={(e) => setFormData({ ...formData, targetId: e.target.value })}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Select a device or group</option>
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Action *</label>
              <select
                value={formData.action}
                onChange={(e) => setFormData({ ...formData, action: e.target.value as "on" | "off" })}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="on">Turn ON</option>
                <option value="off">Turn OFF</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Time *</label>
              <input
                type="time"
                value={formData.time}
                onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
            <input
              type="checkbox"
              id="run-once"
              checked={formData.runOnce}
              onChange={(e) => setFormData({ ...formData, runOnce: e.target.checked, days: e.target.checked ? formData.days.slice(0, 1) : formData.days })}
              className="h-4 w-4 rounded border-border"
            />
            <label htmlFor="run-once" className="text-sm text-foreground">
              Run once and auto delete after execution
            </label>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">
              Days * {formData.runOnce ? "(select exactly 1)" : ""}
            </label>
            <div className="grid grid-cols-4 gap-2">
              {DAYS.map((day) => (
                <label key={day} className="flex cursor-pointer items-center gap-2 rounded border border-transparent px-1 py-1 hover:border-border">
                  <input
                    type="checkbox"
                    checked={formData.days.includes(day)}
                    onChange={() => toggleDay(day)}
                    className="h-4 w-4 rounded border-border"
                  />
                  <span className="text-sm text-foreground">{day}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="enabled"
              checked={formData.enabled}
              onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              className="h-4 w-4 rounded border-border"
            />
            <label htmlFor="enabled" className="text-sm text-muted-foreground">
              Enable this schedule
            </label>
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={() => setScheduleEditorOpen(false)}
              className="flex-1 rounded-lg border border-border px-4 py-2 font-medium text-foreground transition-colors hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              {editingScheduleId ? "Update" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
