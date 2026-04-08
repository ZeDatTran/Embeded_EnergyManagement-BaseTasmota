"use client"

import { ScheduleList } from "@/components/scheduling/schedule-list"
import { ScheduleEditor } from "@/components/scheduling/schedule-editor"
import { Button } from "@/components/ui/button"
import { Plus, Sparkles } from "lucide-react"
import { useUIStore } from "@/lib/store"
import { useGenerateAutoScenarios } from "@/hooks/use-schedules"

export default function SchedulesPage() {
  const { setScheduleEditorOpen } = useUIStore()
  const { mutate: generateAutoScenarios, isPending } = useGenerateAutoScenarios()

  const handleAutoGenerate = () => {
    const confirmed = window.confirm(
      "Tạo lịch bật/tắt tự động dựa trên dữ liệu tiêu thụ 14 ngày gần nhất?"
    )
    if (!confirmed) return

    generateAutoScenarios(
      {
        lookbackDays: 14,
        maxDevices: 8,
        minSamples: 12,
        autoApply: true,
      },
      {
        onSuccess: (result) => {
          window.alert(
            `Đã tạo ${result.createdSchedulesCount} lịch tự động từ ${result.suggestionCount} kịch bản.`
          )
        },
        onError: (error) => {
          window.alert(error instanceof Error ? error.message : "Không thể tạo lịch tự động")
        },
      }
    )
  }

  return (
    <div className="space-y-4">
      {/* Header: stack vertically on very small screens */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Lịch tự động</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Quản lý lịch bật/tắt thiết bị</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleAutoGenerate}
            variant="secondary"
            className="flex-1 gap-2 sm:flex-none"
            disabled={isPending}
          >
            <Sparkles size={16} />
            <span className="sm:inline">{isPending ? "Đang tạo..." : "Tạo tự động"}</span>
          </Button>
          <Button
            onClick={() => setScheduleEditorOpen(true)}
            className="flex-1 gap-2 sm:flex-none"
          >
            <Plus size={16} />
            <span className="sm:inline">Tạo lịch</span>
          </Button>
        </div>
      </div>

      <ScheduleList />
      <ScheduleEditor />
    </div>
  )
}
