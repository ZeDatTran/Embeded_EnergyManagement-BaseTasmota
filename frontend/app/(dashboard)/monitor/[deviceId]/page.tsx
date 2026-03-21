"use client"

import { useParams, useRouter } from "next/navigation"
import { useDevice, useDeviceHistory } from "@/hooks/use-devices"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ArrowLeft, Power, Zap, Gauge, Activity, Clock, ThermometerSun } from "lucide-react"
import { DeviceChart } from "@/components/monitor/device-chart"
import { useUpdateDevice } from "@/hooks/use-devices"
import { useState } from "react"

export default function DeviceDetailPage() {
  const params = useParams()
  const router = useRouter()
  const deviceId = params.deviceId as string
  const [historyPeriod, setHistoryPeriod] = useState<"day" | "week" | "month" | "all">("day")
  
  const { data: device, isLoading, error } = useDevice(deviceId)
  const { data: history, isLoading: historyLoading } = useDeviceHistory(deviceId, historyPeriod, {
    pageSize: 5000,
    chunkDays: 3,
    maxPages: 50,
  })
  const { mutate: updateDevice, isPending } = useUpdateDevice()
  const [isToggling, setIsToggling] = useState(false)

  const handleTogglePower = () => {
    if (!device) return
    setIsToggling(true)
    const isOn = device.attributes?.POWER === "ON"
    updateDevice(
      { id: deviceId, power: isOn ? 0 : 1 },
      {
        onSettled: () => setIsToggling(false),
      }
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Đang tải thông tin thiết bị...</p>
        </div>
      </div>
    )
  }

  if (error || !device) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <p className="text-red-500 mb-4">Không tìm thấy thiết bị</p>
        <Button onClick={() => router.back()} variant="outline">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Quay lại
        </Button>
      </div>
    )
  }

  const isOn = device.attributes?.POWER === "ON"
  const telemetry = device.telemetry || {}
  
  const voltage = parseFloat(String(telemetry["ENERGY-Voltage"] ?? "0"))
  const current = parseFloat(String(telemetry["ENERGY-Current"] ?? "0"))
  const power = parseFloat(String(telemetry["ENERGY-Power"] ?? "0"))
  const energyToday = parseFloat(String(telemetry["ENERGY-Today"] ?? "0"))
  const energyTotal = parseFloat(String(telemetry["ENERGY-Total"] ?? "0"))
  const powerFactor = parseFloat(String(telemetry["ENERGY-Factor"] ?? "0"))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button onClick={() => router.back()} variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              {device.name || device.type || "Thiết bị"}
              <Badge variant={isOn ? "default" : "secondary"}>
                {isOn ? "Đang bật" : "Đang tắt"}
              </Badge>
            </h1>
            <p className="text-muted-foreground">{device.location || "Không xác định"}</p>
          </div>
        </div>
        <Button 
          onClick={handleTogglePower}
          disabled={isToggling || isPending}
          variant={isOn ? "destructive" : "default"}
          size="lg"
        >
          <Power className="mr-2 h-5 w-5" />
          {isOn ? "Tắt thiết bị" : "Bật thiết bị"}
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <Zap className="h-4 w-4" />
              Điện áp
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{voltage.toFixed(1)} V</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <Activity className="h-4 w-4" />
              Dòng điện
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{current.toFixed(3)} A</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <Gauge className="h-4 w-4" />
              Công suất
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{power.toFixed(1)} W</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <ThermometerSun className="h-4 w-4" />
              Hệ số CS
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{powerFactor.toFixed(2)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              Hôm nay
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{energyToday.toFixed(3)} kWh</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1">
              <Zap className="h-4 w-4" />
              Tổng cộng
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{energyTotal.toFixed(2)} kWh</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Lịch sử:</span>
        <Button
          variant={historyPeriod === "day" ? "default" : "outline"}
          size="sm"
          onClick={() => setHistoryPeriod("day")}
        >
          24h
        </Button>
        <Button
          variant={historyPeriod === "week" ? "default" : "outline"}
          size="sm"
          onClick={() => setHistoryPeriod("week")}
        >
          7 ngày
        </Button>
        <Button
          variant={historyPeriod === "month" ? "default" : "outline"}
          size="sm"
          onClick={() => setHistoryPeriod("month")}
        >
          30 ngày
        </Button>
        <Button
          variant={historyPeriod === "all" ? "default" : "outline"}
          size="sm"
          onClick={() => setHistoryPeriod("all")}
        >
          Toàn bộ
        </Button>
      </div>

      <Tabs defaultValue="power" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="power">Công suất</TabsTrigger>
          <TabsTrigger value="voltage">Điện áp</TabsTrigger>
          <TabsTrigger value="current">Dòng điện</TabsTrigger>
          <TabsTrigger value="energy">Năng lượng</TabsTrigger>
        </TabsList>
        
        <TabsContent value="power">
          <Card>
            <CardHeader>
              <CardTitle>Biểu đồ Công suất</CardTitle>
              <CardDescription>Công suất tiêu thụ theo thời gian (W)</CardDescription>
            </CardHeader>
            <CardContent>
              <DeviceChart 
                data={history || []} 
                dataKey="power" 
                color="#3b82f6"
                unit="W"
                isLoading={historyLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="voltage">
          <Card>
            <CardHeader>
              <CardTitle>Biểu đồ Điện áp</CardTitle>
              <CardDescription>Điện áp theo thời gian (V)</CardDescription>
            </CardHeader>
            <CardContent>
              <DeviceChart 
                data={history || []} 
                dataKey="voltage" 
                color="#10b981"
                unit="V"
                isLoading={historyLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="current">
          <Card>
            <CardHeader>
              <CardTitle>Biểu đồ Dòng điện</CardTitle>
              <CardDescription>Dòng điện theo thời gian (A)</CardDescription>
            </CardHeader>
            <CardContent>
              <DeviceChart 
                data={history || []} 
                dataKey="current" 
                color="#f59e0b"
                unit="A"
                isLoading={historyLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="energy">
          <Card>
            <CardHeader>
              <CardTitle>Biểu đồ Năng lượng</CardTitle>
              <CardDescription>Năng lượng tiêu thụ theo thời gian (kWh)</CardDescription>
            </CardHeader>
            <CardContent>
              <DeviceChart 
                data={history || []} 
                dataKey="energy" 
                color="#8b5cf6"
                unit="kWh"
                isLoading={historyLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Device Info */}
      <Card>
        <CardHeader>
          <CardTitle>Thông tin thiết bị</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">ID thiết bị</p>
              <p className="font-mono text-sm">{device.id}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Loại</p>
              <p className="capitalize">{device.type || "N/A"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Vị trí</p>
              <p>{device.location || "N/A"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Trạng thái</p>
              <p>{isOn ? "Hoạt động" : "Không hoạt động"}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
