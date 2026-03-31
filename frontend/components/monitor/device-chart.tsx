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

  // Format data for chart based on period
  const chartData = data.map((item) => {
    const date = new Date(item.timestamp)
    let time = ""
    
    if (period === "day") {
      // For day: show only hour (00, 01, 02, ..., 23)
      const hour = date.getHours().toString().padStart(2, "0")
      time = `${hour}h`
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
                          {Number(payload[0].value).toFixed(2)} {unit}
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
