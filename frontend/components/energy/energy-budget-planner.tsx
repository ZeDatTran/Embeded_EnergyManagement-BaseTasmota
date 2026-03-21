"use client"

import { useEffect, useState, useTransition } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  applyRecommendationRun,
  approveRecommendationAction,
  fetchCurrentBudget,
  fetchRecommendationActions,
  generateEnergyPlan,
  rejectRecommendationAction,
  saveCurrentBudget,
  type BudgetAnalysis,
  type EnergyBudgetProfile,
  type RecommendationAction,
  type RecommendationRun,
} from "@/lib/api"
import { formatCurrency, formatEnergy } from "@/lib/utils"

const CURRENT_MONTH = new Date().toISOString().slice(0, 7)

export function EnergyBudgetPlanner() {
  const [budget, setBudget] = useState<EnergyBudgetProfile | null>(null)
  const [analysis, setAnalysis] = useState<BudgetAnalysis | null>(null)
  const [actions, setActions] = useState<RecommendationAction[]>([])
  const [activeRun, setActiveRun] = useState<RecommendationRun | null>(null)
  const [monthKey, setMonthKey] = useState(CURRENT_MONTH)
  const [targetBillVnd, setTargetBillVnd] = useState("1200000")
  const [warningThresholdPercent, setWarningThresholdPercent] = useState("0.9")
  const [optimizationMode, setOptimizationMode] = useState<"manual" | "assisted" | "automatic">("assisted")
  const [autoApply, setAutoApply] = useState(false)
  const [strategy, setStrategy] = useState<"conservative" | "balanced" | "aggressive">("balanced")
  const [planningHorizonDays, setPlanningHorizonDays] = useState("3")
  const [status, setStatus] = useState<string>("")
  const [isPending, startTransition] = useTransition()

  const loadBudget = async () => {
    try {
      const result = await fetchCurrentBudget(monthKey)
      setBudget(result.budget)
      setAnalysis(result.analysis)
      if (result.budget) {
        setTargetBillVnd(String(Math.round(result.budget.target_bill_vnd)))
        setWarningThresholdPercent(String(result.budget.warning_threshold_percent))
        setOptimizationMode(result.budget.optimization_mode)
        setAutoApply(Boolean(result.budget.auto_apply_recommendations))
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Không thể tải dữ liệu ngân sách")
    }
  }

  useEffect(() => {
    loadBudget()
  }, [monthKey])

  const handleSaveBudget = () => {
    startTransition(async () => {
      try {
        const result = await saveCurrentBudget({
          monthKey,
          targetBillVnd: Number(targetBillVnd),
          warningThresholdPercent: Number(warningThresholdPercent),
          optimizationMode,
          autoApplyRecommendations: autoApply,
        })
        setBudget(result.budget)
        setAnalysis(result.analysis)
        setStatus("Đã lưu ngân sách điện thành công")
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Không thể lưu ngân sách")
      }
    })
  }

  const handleGeneratePlan = () => {
    startTransition(async () => {
      try {
        const result = await generateEnergyPlan({
          monthKey,
          planningHorizonDays: Number(planningHorizonDays),
          strategy,
        })
        setAnalysis(result.analysis)
        setActions(result.actions)
        setActiveRun(result.run)
        setStatus(result.summary.message)
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Không thể sinh khuyến nghị")
      }
    })
  }

  const refreshActions = async (runId: string) => {
    const refreshed = await fetchRecommendationActions(runId)
    setActions(refreshed)
  }

  const handleApprove = (actionId: string) => {
    startTransition(async () => {
      try {
        await approveRecommendationAction(actionId)
        if (activeRun) {
          await refreshActions(activeRun.id)
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Không thể duyệt action")
      }
    })
  }

  const handleReject = (actionId: string) => {
    startTransition(async () => {
      try {
        await rejectRecommendationAction(actionId)
        if (activeRun) {
          await refreshActions(activeRun.id)
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Không thể từ chối action")
      }
    })
  }

  const handleApplyPlan = () => {
    if (!activeRun) return
    startTransition(async () => {
      try {
        const result = await applyRecommendationRun(activeRun.id)
        setStatus(`Đã tạo ${result.createdSchedulesCount} lịch tối ưu`) 
        await refreshActions(activeRun.id)
        await loadBudget()
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Không thể áp dụng khuyến nghị")
      }
    })
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Ngân sách điện cuối tháng</CardTitle>
          <CardDescription>
            Đặt mức tiền điện mục tiêu để hệ thống sinh lịch bật tắt plug phù hợp với thói quen sử dụng.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-2">
              <Label htmlFor="monthKey">Tháng áp dụng</Label>
              <Input id="monthKey" type="month" value={monthKey} onChange={(e) => setMonthKey(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="targetBillVnd">Mục tiêu tiền điện (VND)</Label>
              <Input id="targetBillVnd" type="number" min="1000" value={targetBillVnd} onChange={(e) => setTargetBillVnd(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="warningThreshold">Ngưỡng cảnh báo</Label>
              <Input id="warningThreshold" type="number" min="0.1" max="1.5" step="0.05" value={warningThresholdPercent} onChange={(e) => setWarningThresholdPercent(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="optimizationMode">Chế độ tối ưu</Label>
              <select
                id="optimizationMode"
                value={optimizationMode}
                onChange={(e) => setOptimizationMode(e.target.value as "manual" | "assisted" | "automatic")}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="manual">Manual</option>
                <option value="assisted">Assisted</option>
                <option value="automatic">Automatic</option>
              </select>
            </div>
            <div className="flex items-end justify-between rounded-md border px-4 py-3">
              <div>
                <p className="text-sm font-medium">Tự áp dụng</p>
                <p className="text-xs text-muted-foreground">Dùng khi các plug đã khai báo đủ constraint</p>
              </div>
              <Switch checked={autoApply} onCheckedChange={setAutoApply} />
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button onClick={handleSaveBudget} disabled={isPending}>Lưu ngân sách</Button>
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Label htmlFor="strategy">Chiến lược</Label>
              <select
                id="strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as "conservative" | "balanced" | "aggressive")}
                className="bg-transparent text-sm"
              >
                <option value="conservative">Conservative</option>
                <option value="balanced">Balanced</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </div>
            <div className="flex items-center gap-3 rounded-md border px-3 py-2">
              <Label htmlFor="planningHorizon">Số ngày lập kế hoạch</Label>
              <Input
                id="planningHorizon"
                type="number"
                min="1"
                max="7"
                value={planningHorizonDays}
                onChange={(e) => setPlanningHorizonDays(e.target.value)}
                className="w-20"
              />
            </div>
            <Button variant="secondary" onClick={handleGeneratePlan} disabled={isPending}>Sinh khuyến nghị</Button>
            <Button variant="outline" onClick={handleApplyPlan} disabled={isPending || !activeRun || actions.length === 0}>Áp dụng vào lịch</Button>
          </div>
          {status ? <p className="text-sm text-muted-foreground">{status}</p> : null}
        </CardContent>
      </Card>

      {analysis ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card>
            <CardHeader>
              <CardDescription>Tiền điện đã dùng</CardDescription>
              <CardTitle>{formatCurrency(analysis.actualSpentVndMonth)}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{formatEnergy(analysis.actualConsumedKwhMonth)} từ đầu tháng</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Dự báo cuối tháng</CardDescription>
              <CardTitle>{formatCurrency(analysis.forecastBillVnd)}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{formatEnergy(analysis.forecastKwhMonth)} tổng tháng</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Mục tiêu đặt ra</CardDescription>
              <CardTitle>{formatCurrency(analysis.targetBillVnd || 0)}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">Tương đương {formatEnergy(analysis.targetKwhMonth || 0)}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Cần cắt giảm thêm</CardDescription>
              <CardTitle>{formatCurrency(analysis.overrunVnd)}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{formatEnergy(analysis.requiredReductionKwh)} cần giảm</CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Top plug tiêu thụ nhiều nhất</CardTitle>
          <CardDescription>Hệ thống ưu tiên tối ưu các plug có mức tiêu thụ cao và có thể điều khiển tự động.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {analysis?.topConsumers?.length ? analysis.topConsumers.slice(0, 5).map((device) => (
            <div key={device.deviceId} className="flex items-center justify-between rounded-md border px-4 py-3 text-sm">
              <div>
                <p className="font-medium">{device.deviceName}</p>
                <p className="text-muted-foreground">{device.priority || "unconfigured"} {device.autoControllable ? "· auto" : "· manual"}</p>
              </div>
              <div className="text-right">
                <p className="font-medium">{formatEnergy(device.totalKwh || device.energyKwh || 0)}</p>
                <p className="text-muted-foreground">{Math.round(device.avgPowerW || 0)} W</p>
              </div>
            </div>
          )) : <p className="text-sm text-muted-foreground">Chưa có dữ liệu phân tích theo plug.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Khuyến nghị tối ưu mới nhất</CardTitle>
          <CardDescription>
            Chọn duyệt hoặc loại từng hành động trước khi đẩy xuống scheduler hiện tại.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {actions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có khuyến nghị nào. Hãy sinh kế hoạch sau khi đặt ngân sách.</p>
          ) : (
            actions.map((action) => (
              <div key={action.id} className="rounded-lg border p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="space-y-1">
                    <p className="font-medium">{action.deviceName || action.device_id}</p>
                    <p className="text-sm text-muted-foreground">{action.reason_text || action.reason_code}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(action.proposed_start).toLocaleString("vi-VN")} {action.proposed_end ? `-> ${new Date(action.proposed_end).toLocaleString("vi-VN")}` : ""}
                    </p>
                  </div>
                  <div className="grid gap-1 text-sm lg:min-w-64">
                    <p>Tiết kiệm ước tính: <span className="font-medium">{formatEnergy(action.estimated_energy_saved_kwh)}</span></p>
                    <p>Giảm chi phí: <span className="font-medium">{formatCurrency(action.estimated_cost_saved_vnd)}</span></p>
                    <p>Trạng thái: <span className="font-medium uppercase">{action.approval_status}</span></p>
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => handleApprove(action.id)} disabled={isPending || action.approval_status === "approved" || action.approval_status === "applied"}>Duyệt</Button>
                  <Button size="sm" variant="outline" onClick={() => handleReject(action.id)} disabled={isPending || action.approval_status === "rejected"}>Loại</Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}