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
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Schedules</h1>
        <div className="flex items-center gap-2">
          <Button onClick={handleAutoGenerate} variant="secondary" className="gap-2" disabled={isPending}>
            <Sparkles size={18} />
            {isPending ? "Generating..." : "Auto Generate"}
          </Button>
          <Button onClick={() => setScheduleEditorOpen(true)} className="gap-2">
            <Plus size={18} />
            New Schedule
          </Button>
        </div>
      </div>
      <ScheduleList />
      <ScheduleEditor />
    </div>
  )
}
