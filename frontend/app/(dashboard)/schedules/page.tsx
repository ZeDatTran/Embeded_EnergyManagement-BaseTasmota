"use client"

import { useState } from "react"
import { ScheduleList } from "@/components/scheduling/schedule-list"
import { ScheduleEditor } from "@/components/scheduling/schedule-editor"
import { AutoScenarioPreview } from "@/components/scheduling/auto-scenario-preview"
import { Button } from "@/components/ui/button"
import { Plus, Sparkles } from "lucide-react"
import { useUIStore } from "@/lib/store"
import { useGenerateAutoScenarios } from "@/hooks/use-schedules"
import type { AutoScenarioResponse } from "@/hooks/use-schedules"
import { useToast } from "@/hooks/use-toast"

export default function SchedulesPage() {
  const { setScheduleEditorOpen } = useUIStore()
  const { mutate: generateAutoScenarios, isPending } = useGenerateAutoScenarios()
  const { toast } = useToast()
  const [previewData, setPreviewData] = useState<AutoScenarioResponse | null>(null)

  const handleAutoGenerate = () => {
    generateAutoScenarios(
      {
        lookbackDays: 14,
        maxDevices: 8,
        minSamples: 12,
        autoApply: false, // Preview first — user approves before saving
      },
      {
        onSuccess: (result) => {
          if (!result.suggestions || result.suggestions.length === 0) {
            toast({
              title: "Không đủ dữ liệu",
              description: "Cần ít nhất 12 mẫu từ các thiết bị để tạo lịch tự động. Hãy thử lại sau khi thiết bị hoạt động thêm.",
              variant: "destructive",
            })
            return
          }
          setPreviewData(result)
        },
        onError: (error) => {
          toast({
            title: "Lỗi tạo lịch tự động",
            description: error instanceof Error ? error.message : "Không thể tạo lịch tự động",
            variant: "destructive",
          })
        },
      }
    )
  }

  return (
    <div className="space-y-4">
      {/* Header: stacks vertically on mobile */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Lịch tự động</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Quản lý lịch bật/tắt thiết bị</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleAutoGenerate}
            variant="secondary"
            className="flex-1 gap-2 sm:flex-none"
            disabled={isPending}
          >
            <Sparkles size={16} />
            {isPending ? "Đang phân tích..." : "Tạo tự động"}
          </Button>
          <Button
            onClick={() => setScheduleEditorOpen(true)}
            className="flex-1 gap-2 sm:flex-none"
          >
            <Plus size={16} />
            Tạo lịch
          </Button>
        </div>
      </div>

      <ScheduleList />
      <ScheduleEditor />

      {/* Preview modal — only shown after analysis returns suggestions */}
      {previewData && (
        <AutoScenarioPreview
          suggestions={previewData.suggestions}
          onClose={() => setPreviewData(null)}
          onApplied={(count) => {
            toast({
              title: "Đã tạo lịch thành công",
              description: `Áp dụng ${count} lịch tự động.`,
            })
            setPreviewData(null)
          }}
        />
      )}
    </div>
  )
}
