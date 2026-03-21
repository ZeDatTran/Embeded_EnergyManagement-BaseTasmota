import { Card, CardContent } from "@/components/ui/card"
import { Icons } from "@/components/icons"
import { formatEnergy, formatCurrency } from "@/lib/utils"
import type { EnergyData } from "@/lib/api"
import type { EnergySummaryData } from "@/lib/api"

interface EnergyStatsProps {
  data: EnergyData[]
  period: "day" | "week" | "month"
  summary?: EnergySummaryData | null
}

export function EnergyStats({ data, period, summary }: EnergyStatsProps) {
  const chartTotalConsumption = data.reduce((sum, item) => sum + item.consumption, 0)
  const chartTotalCost = data.reduce((sum, item) => sum + item.cost, 0)
  const shouldUseSummary = (period === "day" || period === "month") && !!summary
  const totalConsumption = shouldUseSummary ? (summary?.totalConsumption || 0) : chartTotalConsumption
  const totalCost = shouldUseSummary ? (summary?.totalCost || 0) : chartTotalCost
  const avgConsumption = totalConsumption / data.length || 0
  const maxConsumption = Math.max(...data.map((item) => item.consumption), 0)

  const periodLabel = {
    day: "hôm nay",
    week: "tuần này",
    month: "tháng này",
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Tổng tiêu thụ</p>
              <p className="text-2xl font-bold">{formatEnergy(totalConsumption)}</p>
              <p className="text-xs text-muted-foreground">{periodLabel[period]}</p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-500/10">
              <Icons.energy className="h-6 w-6 text-blue-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Tổng chi phí</p>
              <p className="text-2xl font-bold">{formatCurrency(totalCost)}</p>
              <p className="text-xs text-muted-foreground">{periodLabel[period]}</p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-yellow-500/10">
              <Icons.chart className="h-6 w-6 text-yellow-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Trung bình</p>
              <p className="text-2xl font-bold">{formatEnergy(avgConsumption)}</p>
              <p className="text-xs text-muted-foreground">mỗi {period === "day" ? "giờ" : "ngày"}</p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
              <Icons.activity className="h-6 w-6 text-green-500" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Cao nhất</p>
              <p className="text-2xl font-bold">{formatEnergy(maxConsumption)}</p>
              <p className="text-xs text-muted-foreground">trong kỳ</p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10">
              <Icons.trendingUp className="h-6 w-6 text-red-500" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
