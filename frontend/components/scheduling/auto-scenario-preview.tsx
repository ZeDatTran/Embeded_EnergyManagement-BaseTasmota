"use client"

import { useState, useCallback } from "react"
import { X, Zap, ZapOff, Clock, BarChart2, ChevronDown, ChevronUp, Calendar } from "lucide-react"
import { useCreateSchedule } from "@/hooks/use-schedules"
import { useToast } from "@/hooks/use-toast"
import type { AutoScenarioResponse } from "@/hooks/use-schedules"

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
type Suggestion = AutoScenarioResponse["suggestions"][number]
type PeakEntry = Suggestion["peaks"][number]

interface EditItem {
  localId: string
  name: string
  targetId: string
  action: "on" | "off"
  time: string
  days: string[]
  enabled: boolean
  selected: boolean
  deviceName: string
  peakWindow: [number, number]
  totalKwh: number
}

interface AutoScenarioPreviewProps {
  suggestions: Suggestion[]
  onClose: () => void
  onApplied: (count: number) => void
}

export function AutoScenarioPreview({ suggestions, onClose, onApplied }: AutoScenarioPreviewProps) {
  const { toast } = useToast()
  const { mutateAsync: createSchedule } = useCreateSchedule()
  const [isApplying, setIsApplying] = useState(false)
  const [expandedDevices, setExpandedDevices] = useState<Set<string>>(
    () => new Set(suggestions.map((s) => s.deviceId))
  )

  // Flatten all peaks of all devices into editable items
  const [items, setItems] = useState<EditItem[]>(() => {
    const result: EditItem[] = []
    suggestions.forEach((s) => {
      s.peaks.forEach((peak, pi) => {
        const base = `${s.deviceId}|p${pi}`
        result.push({
          localId: `${base}|on`,
          ...peak.onSchedule,
          selected: true,
          deviceName: s.deviceName,
          peakWindow: peak.analysis.peakWindow,
          totalKwh: peak.analysis.totalKwhInWindow,
        })
        result.push({
          localId: `${base}|off`,
          ...peak.offSchedule,
          selected: true,
          deviceName: s.deviceName,
          peakWindow: peak.analysis.peakWindow,
          totalKwh: peak.analysis.totalKwhInWindow,
        })
      })
    })
    return result
  })

  const selectedCount = items.filter((i) => i.selected).length

  const updateItem = useCallback((localId: string, changes: Partial<EditItem>) => {
    setItems((prev) => prev.map((item) => (item.localId === localId ? { ...item, ...changes } : item)))
  }, [])

  // Toggle a day for a specific item (keeping DAYS order)
  const toggleDay = useCallback((localId: string, day: string) => {
    setItems((prev) =>
      prev.map((item) => {
        if (item.localId !== localId) return item
        const next = item.days.includes(day)
          ? item.days.filter((d) => d !== day)
          : [...item.days, day]
        return { ...item, days: DAYS.filter((d) => next.includes(d)) }
      })
    )
  }, [])

  const toggleDevice = (deviceId: string, select: boolean) => {
    setItems((prev) =>
      prev.map((item) => (item.targetId === deviceId ? { ...item, selected: select } : item))
    )
  }

  const toggleExpand = (deviceId: string) => {
    setExpandedDevices((prev) => {
      const next = new Set(prev)
      next.has(deviceId) ? next.delete(deviceId) : next.add(deviceId)
      return next
    })
  }

  const handleApply = async () => {
    const toCreate = items.filter((i) => i.selected && i.days.length > 0)
    if (toCreate.length === 0) {
      toast({
        title: "Chưa chọn lịch nào",
        description: "Hãy chọn ít nhất 1 lịch để áp dụng.",
        variant: "destructive",
      })
      return
    }
    setIsApplying(true)
    let created = 0
    for (const item of toCreate) {
      try {
        await createSchedule({
          name: item.name,
          targetId: item.targetId,
          action: item.action,
          time: item.time,
          days: item.days,
          enabled: true,
          runOnce: false,
        })
        created++
      } catch {
      }
    }
    setIsApplying(false)
    onApplied(created)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4">
      <div className="flex max-h-[92dvh] w-full flex-col rounded-t-2xl border border-border bg-card shadow-xl sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg">
        <div className="relative shrink-0 border-b border-border px-4 py-4 sm:px-6">
          <div className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-muted-foreground/25 sm:hidden" />
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold sm:text-lg">Xem trước lịch tự động</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {suggestions.length} thiết bị · {selectedCount} lịch được chọn
              </p>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              aria-label="Đóng"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          <div className="space-y-3">
            {suggestions.map((s) => {
              const deviceItems = items.filter((i) => i.targetId === s.deviceId)
              const allSelected = deviceItems.length > 0 && deviceItems.every((i) => i.selected)
              const someSelected = deviceItems.some((i) => i.selected)
              const expanded = expandedDevices.has(s.deviceId)

              return (
                <div key={s.deviceId} className="overflow-hidden rounded-lg border border-border">
                  {/* Device header row */}
                  <button
                    type="button"
                    onClick={() => toggleExpand(s.deviceId)}
                    className="flex w-full items-center gap-3 bg-muted/40 px-4 py-3 text-left transition-colors hover:bg-muted/60"
                  >
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected && !allSelected
                      }}
                      onChange={(e) => {
                        e.stopPropagation()
                        toggleDevice(s.deviceId, e.target.checked)
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="h-4 w-4 shrink-0 accent-primary"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-foreground">{s.deviceName}</p>
                      <p className="text-xs text-muted-foreground">
                        {s.analysis.samples} mẫu · {s.peaks.length} khung giờ · {s.days.join(", ")}
                      </p>
                    </div>
                    <div className="shrink-0 text-muted-foreground">
                      {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  </button>
                  {expanded && (
                    <div className="divide-y divide-border">
                      {s.peaks.map((peak, pi) => {
                        const onItem = items.find((i) => i.localId === `${s.deviceId}|p${pi}|on`)
                        const offItem = items.find((i) => i.localId === `${s.deviceId}|p${pi}|off`)
                        if (!onItem || !offItem) return null
                        return (
                          <PeakPanel
                            key={pi}
                            peakIndex={pi}
                            totalPeaks={s.peaks.length}
                            peak={peak}
                            onItem={onItem}
                            offItem={offItem}
                            onUpdate={updateItem}
                            onToggleDay={toggleDay}
                          />
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        <div className="shrink-0 border-t border-border px-4 py-4 sm:px-6">
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              Hủy
            </button>
            <button
              onClick={handleApply}
              disabled={selectedCount === 0 || isApplying}
              className="flex-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {isApplying ? "Đang áp dụng..." : `Áp dụng ${selectedCount} lịch`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
function PeakPanel({
  peakIndex,
  totalPeaks,
  peak,
  onItem,
  offItem,
  onUpdate,
  onToggleDay,
}: {
  peakIndex: number
  totalPeaks: number
  peak: PeakEntry
  onItem: EditItem
  offItem: EditItem
  onUpdate: (localId: string, changes: Partial<EditItem>) => void
  onToggleDay: (localId: string, day: string) => void
}) {
  return (
    <div className="space-y-3 p-4">
      {/* Peak label + analysis */}
      <div className="flex flex-wrap items-center gap-2">
        {totalPeaks > 1 && (
          <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200">
            Khung giờ {peakIndex + 1}
          </span>
        )}
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <BarChart2 size={11} />
          Peak {peak.analysis.peakWindow[0]}h–{peak.analysis.peakWindow[1] + 1}h ·{" "}
          {peak.analysis.totalKwhInWindow.toFixed(3)} kWh (14 ngày)
        </span>
      </div>
      <ScheduleRow item={onItem} onUpdate={onUpdate} />
      <ScheduleRow item={offItem} onUpdate={onUpdate} />
      <div className="space-y-1.5">
        <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <Calendar size={11} />
          Ngày áp dụng
        </p>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((day) => {
            const selected = onItem.days.includes(day)
            return (
              <button
                key={day}
                type="button"
                onClick={() => {
                  onToggleDay(onItem.localId, day)
                  onToggleDay(offItem.localId, day)
                }}
                className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${selected
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
    </div>
  )
}
function ScheduleRow({
  item,
  onUpdate,
}: {
  item: EditItem
  onUpdate: (localId: string, changes: Partial<EditItem>) => void
}) {
  return (
    <div className="flex items-center gap-3">
      <input
        type="checkbox"
        checked={item.selected}
        onChange={(e) => onUpdate(item.localId, { selected: e.target.checked })}
        className="h-4 w-4 shrink-0 accent-primary"
      />
      <span
        className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${item.action === "on"
            ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
            : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
          }`}
      >
        {item.action === "on" ? <Zap size={10} /> : <ZapOff size={10} />}
        {item.action === "on" ? "Bật" : "Tắt"}
      </span>
      <div className="flex items-center gap-1.5">
        <Clock size={12} className="shrink-0 text-muted-foreground" />
        <input
          type="time"
          value={item.time}
          onChange={(e) => onUpdate(item.localId, { time: e.target.value })}
          className="w-[90px] rounded-lg border border-input bg-background px-2 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{item.name}</span>
    </div>
  )
}
