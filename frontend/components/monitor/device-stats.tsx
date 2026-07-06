"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"

interface DeviceStatsProps {
  data: Array<{
    timestamp: string
    power?: number
    voltage?: number
    current?: number
    energy?: number
  }>
}

export function DeviceStats({ data }: DeviceStatsProps) {
  if (!data || data.length === 0) {
    return null
  }

  // Calculate statistics
  const powerValues = data.map((d) => d.power || 0).filter((v) => v > 0)
  const voltageValues = data.map((d) => d.voltage || 0).filter((v) => v > 0)
  const currentValues = data.map((d) => d.current || 0).filter((v) => v > 0)

  const calcStats = (values: number[]) => {
    if (values.length === 0) return { avg: 0, min: 0, max: 0, trend: 0 }
    const avg = values.reduce((a, b) => a + b, 0) / values.length
    const min = Math.min(...values)
    const max = Math.max(...values)
    // Calculate trend (compare last 10% with first 10%)
    const tenPercent = Math.max(1, Math.floor(values.length * 0.1))
    const firstAvg = values.slice(0, tenPercent).reduce((a, b) => a + b, 0) / tenPercent
    const lastAvg = values.slice(-tenPercent).reduce((a, b) => a + b, 0) / tenPercent
    const trend = firstAvg > 0 ? ((lastAvg - firstAvg) / firstAvg) * 100 : 0
    return { avg, min, max, trend }
  }

  const powerStats = calcStats(powerValues)
  const voltageStats = calcStats(voltageValues)
  const currentStats = calcStats(currentValues)

  const TrendIcon = ({ trend }: { trend: number }) => {
    if (trend > 5) return <TrendingUp className="h-4 w-4 text-red-500" />
    if (trend < -5) return <TrendingDown className="h-4 w-4 text-green-500" />
    return <Minus className="h-4 w-4 text-gray-500" />
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Thống kê Công suất</CardTitle>
          <CardDescription>Trong khoảng thời gian đã chọn</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Trung bình:</span>
              <span className="font-medium">{powerStats.avg.toFixed(1)} W</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Thấp nhất:</span>
              <span className="font-medium">{powerStats.min.toFixed(1)} W</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Cao nhất:</span>
              <span className="font-medium">{powerStats.max.toFixed(1)} W</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Xu hướng:</span>
              <span className="font-medium flex items-center gap-1">
                <TrendIcon trend={powerStats.trend} />
                {Math.abs(powerStats.trend).toFixed(1)}%
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Thống kê Điện áp</CardTitle>
          <CardDescription>Trong khoảng thời gian đã chọn</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Trung bình:</span>
              <span className="font-medium">{voltageStats.avg.toFixed(1)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Thấp nhất:</span>
              <span className="font-medium">{voltageStats.min.toFixed(1)} V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Cao nhất:</span>
              <span className="font-medium">{voltageStats.max.toFixed(1)} V</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Xu hướng:</span>
              <span className="font-medium flex items-center gap-1">
                <TrendIcon trend={voltageStats.trend} />
                {Math.abs(voltageStats.trend).toFixed(1)}%
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Thống kê Dòng điện</CardTitle>
          <CardDescription>Trong khoảng thời gian đã chọn</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Trung bình:</span>
              <span className="font-medium">{currentStats.avg.toFixed(3)} A</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Thấp nhất:</span>
              <span className="font-medium">{currentStats.min.toFixed(3)} A</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Cao nhất:</span>
              <span className="font-medium">{currentStats.max.toFixed(3)} A</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground">Xu hướng:</span>
              <span className="font-medium flex items-center gap-1">
                <TrendIcon trend={currentStats.trend} />
                {Math.abs(currentStats.trend).toFixed(1)}%
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
