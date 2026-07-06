"use client"

import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts"
import { Skeleton } from "@/components/ui/skeleton"

interface DeviceChartProps {
  data: Array<{
    timestamp: string
    power?: number
    voltage?: number
    current?: number
    energy?: number
  }>
  dataKey: "power" | "voltage" | "current" | "energy"
  color: string
  unit: string
  isLoading?: boolean
  period?: "day" | "week" | "month" | "all"
}

export function DeviceChart({ data, dataKey, color, unit, isLoading, period = "day" }: DeviceChartProps) {
  if (isLoading) {
    return <Skeleton className="h-[350px] w-full" />
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-[350px] flex items-center justify-center text-muted-foreground">
        <p>Chưa có dữ liệu lịch sử cho thiết bị này</p>
      </div>
    )
  }

  const sortedData = [...data].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  // For energy chart:
  // - If series already has resets (drops), keep raw values.
  // - If series looks like per-bucket deltas, convert to cumulative per day
  //   so day boundaries still show a drop then rise.
  const maybeCumulativeEnergyData = (() => {
    if (dataKey !== "energy") return sortedData

    const values = sortedData.map((item) => Number(item.energy || 0))
    let decreases = 0
    for (let i = 1; i < values.length; i++) {
      if (values[i] + 1e-9 < values[i - 1]) {
        decreases += 1
      }
    }

    const hasResetPattern = decreases > 0

    if (hasResetPattern) {
      return sortedData
    }

    let running = 0
    let currentDay = ""
    return sortedData.map((item) => {
      const ts = new Date(item.timestamp)
      const dayKey = `${ts.getFullYear()}-${(ts.getMonth() + 1).toString().padStart(2, "0")}-${ts
        .getDate()
        .toString()
        .padStart(2, "0")}`

      if (dayKey !== currentDay) {
        currentDay = dayKey
        running = 0
      }

      running += Math.max(0, Number(item.energy || 0))
      return {
        ...item,
        energy: running,
      }
    })
  })()

  const formatValue = (value: number) => {
    if (dataKey === "energy") {
      if (value >= 1) return value.toFixed(3)
      return value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")
    }
    if (dataKey === "current") return value.toFixed(3)
    if (dataKey === "voltage") return value.toFixed(1)
    if (dataKey === "power") return value.toFixed(1)
    return value.toFixed(2)
  }

  // Format data for chart based on period
  const chartData = maybeCumulativeEnergyData.map((item) => {
    const date = new Date(item.timestamp)
    let time = ""
    
    if (period === "day") {
      // For day: keep hour and minute to match real telemetry intervals.
      const hour = date.getHours().toString().padStart(2, "0")
      const minute = date.getMinutes().toString().padStart(2, "0")
      time = `${hour}:${minute}`
    } else if (period === "week") {
      // For week: show day abbreviation (e.g., Mon, Tue)
      time = date.toLocaleDateString("vi-VN", {
        weekday: "short",
        day: "2-digit",
      })
    } else if (period === "month") {
      // For month: show day/month (e.g., 21/3, 02/3)
      const day = date.getDate()
      const month = date.getMonth() + 1
      time = `${day}/${month}`
    } else {
      // For all: show day/month (e.g., 21/3, 02/3)
      const day = date.getDate()
      const month = date.getMonth() + 1
      time = `${day}/${month}`
    }
    
    return {
      ...item,
      time,
      fullTimestamp: date.toLocaleString("vi-VN"),
      value: item[dataKey] || 0,
    }
  })

  return (
    <div className="h-[350px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis 
            dataKey="time" 
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis 
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `${value}`}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const item = payload[0].payload
                return (
                  <div className="rounded-lg border bg-background p-3 shadow-md">
                    <div className="space-y-1">
                      <p className="text-sm font-medium">{item.fullTimestamp}</p>
                      <p className="text-sm text-muted-foreground">
                        Giá trị:{" "}
                        <span className="font-semibold" style={{ color }}>
                          {formatValue(Number(payload[0].value || 0))} {unit}
                        </span>
                      </p>
                    </div>
                  </div>
                )
              }
              return null
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: color }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
