"use client"

import { useEffect, useState } from "react"
import { EnergyChart } from "@/components/energy/energy-chart"
import { EnergyStats } from "@/components/energy/energy-stats"
import { ThresholdAlert } from "@/components/energy/threshold-alert"
import { AIPredictEnergy } from "@/components/energy/AI-predict-energy"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fetchEnergyData, fetchEnergySummary, type EnergyData, type EnergySummaryData } from "@/lib/api"
import { useSocket } from "@/context/SocketContext"

interface DeviceCurrentData {
  deviceId: string
  deviceName: string
  current: number
}

export default function EnergyPage() {
  const [period, setPeriod] = useState<"day" | "week" | "month">("day")
  const [data, setData] = useState<EnergyData[]>([])
  const [summary, setSummary] = useState<EnergySummaryData | null>(null)
  const [loading, setLoading] = useState(true)
  // Track all devices' ENERGY-Current
  const [devicesCurrentData, setDevicesCurrentData] = useState<Map<string, DeviceCurrentData>>(new Map())
  const { socket, isConnected } = useSocket()

  useEffect(() => {
    loadData()
  }, [period])

  // Subscribe to dashboard socket to collect ENERGY-Current for all devices
  useEffect(() => {
    if (!socket || !isConnected) return

    // Join dashboard room to receive real-time updates
    socket.emit("join_dashboard")
    console.log("Energy page: Joined dashboard room")

    const onDashboardUpdate = (payload: any) => {
      console.log("Energy page received dashboard_update:", payload)

      try {
        // Handle initial snapshot (array of all devices)
        if (payload.data && Array.isArray(payload.data)) {
          console.log("Processing initial snapshot:", payload.data.length, "devices")
          const newMap = new Map<string, DeviceCurrentData>()
          payload.data.forEach((item: any) => {
            const current = parseFloat(item.telemetry?.["ENERGY-Current"] || "0")
            newMap.set(item.id, {
              deviceId: item.id,
              deviceName: item.name,
              current: current
            })
          })
          setDevicesCurrentData(newMap)
          console.log("Updated devices current data from snapshot")
        }
        // Handle individual device update
        else if (payload?.device_id && payload?.data) {
          const current = payload.data.telemetry?.["ENERGY-Current"]
          console.log(`Device ${payload.device_id} current update:`, current)

          if (current !== undefined && current !== null) {
            const value = Number(current) || 0
            setDevicesCurrentData((prev) => {
              const newMap = new Map(prev)
              const existing = newMap.get(payload.device_id)
              const deviceName = payload.data.metadata?.name || existing?.deviceName || "Unknown Device"
              newMap.set(payload.device_id, {
                deviceId: payload.device_id,
                deviceName: deviceName,
                current: value
              })
              console.log(`Updated device ${payload.device_id} (${deviceName}) current to ${value}A`)
              return newMap
            })
          }
        }
      } catch (e) {
        console.error("Error processing dashboard_update in Energy page", e)
      }
    }

    socket.on("dashboard_update", onDashboardUpdate)

    return () => {
      socket.off("dashboard_update", onDashboardUpdate)
    }
  }, [socket, isConnected])

  const loadData = async () => {
    setLoading(true)
    const [energyData, energySummary] = await Promise.all([
      fetchEnergyData(period),
      fetchEnergySummary(period),
    ])
    setData(energyData)
    setSummary(energySummary)
    setLoading(false)
  }

  // Find device with maximum current
  const getMaxCurrentDevice = (): DeviceCurrentData => {
    if (devicesCurrentData.size === 0) {
      return { deviceId: "", deviceName: "Không có thiết bị", current: 0 }
    }

    let maxDevice: DeviceCurrentData = { deviceId: "", deviceName: "", current: 0 }
    devicesCurrentData.forEach((device) => {
      if (device.current > maxDevice.current) {
        maxDevice = device
      }
    })

    return maxDevice
  }

  const maxCurrentDevice = getMaxCurrentDevice()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-2">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
          <p className="text-sm text-muted-foreground">Đang tải dữ liệu...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Giám sát điện năng</h1>
          <p className="text-sm sm:text-base text-muted-foreground">Theo dõi tiêu thụ điện và chi phí</p>
        </div>
        <Tabs value={period} onValueChange={(v) => setPeriod(v as "day" | "week" | "month")}>
          <TabsList>
            <TabsTrigger value="day">Ngày</TabsTrigger>
            <TabsTrigger value="week">Tuần</TabsTrigger>
            <TabsTrigger value="month">Tháng</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Stats */}
      <EnergyStats data={data} period={period} summary={summary} />

      {/* Main content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Chart - takes 2 columns */}
        <div className="lg:col-span-2">
          <EnergyChart data={data} period={period} />
        </div>

        {/* Threshold alert - takes 1 column */}
        <div>
          {/* Hiển thị giá trị max current hiện tại và tên thiết bị */}
          <ThresholdAlert
            currentAmps={maxCurrentDevice.current}
            deviceName={maxCurrentDevice.deviceName}
          />
        </div>
      </div>
      {/* AI Forecast Component */}
      <AIPredictEnergy />
    </div>
  )
}
