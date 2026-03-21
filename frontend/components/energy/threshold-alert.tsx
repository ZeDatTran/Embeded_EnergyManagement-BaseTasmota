"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Icons } from "@/components/icons"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useSocket } from "@/context/SocketContext"
import { useToast } from "@/hooks/use-toast"

interface ThresholdAlertProps {
  // Giá trị dòng điện hiện tại (A) từ ENERGY-Current
  currentAmps: number
  // Tên thiết bị đang hiển thị
  deviceName: string
}

export function ThresholdAlert({ currentAmps, deviceName }: ThresholdAlertProps) {
  const [enabled, setEnabled] = useState(false)
  const [threshold, setThreshold] = useState("20")
  const [isEditing, setIsEditing] = useState(false)
  const { socket, isConnected } = useSocket()
  const { toast } = useToast()

  const thresholdValue = Number.parseFloat(threshold) || 0
  const percentage = thresholdValue >= 0 && !isNaN(thresholdValue) ? (currentAmps / thresholdValue) * 100 : 0
  const isOverThreshold = !isNaN(thresholdValue) && currentAmps >= thresholdValue

  // Khi component mount, lấy từ LocalStorage ra
  useEffect(() => {
    const savedThreshold = localStorage.getItem(`threshold`)
    if (savedThreshold) {
      setThreshold(savedThreshold)
    }

    const savedEnabled = localStorage.getItem("threshold_enabled")
    if (savedEnabled !== null) {
      setEnabled(savedEnabled === "true")
    }
  }, [deviceName])

  useEffect(() => {
    localStorage.setItem("threshold_enabled", enabled.toString())
  }, [enabled])

  const handleSaveThreshold = () => {
    if (!socket || !isConnected) {
      toast({
        title: "Lỗi kết nối",
        description: "Không thể kết nối đến server",
        variant: "destructive",
      })
      return
    }

    const value = Number.parseFloat(threshold)
    if (isNaN(value) || value < 0) {
      toast({
        title: "Giá trị không hợp lệ",
        description: "Ngưỡng phải là số không âm",
        variant: "destructive",
      })
      return
    }

    // Gửi ngưỡng lên Backend qua Socket
    socket.emit("set_alert_threshold", { threshold: value })

    // Lưu vào LocalStorage
    localStorage.setItem(`threshold`, value.toString())

    toast({
      title: "Đã lưu ngưỡng",
      description: `Ngưỡng cảnh báo: ${value}A`,
    })

    setIsEditing(false)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Cảnh báo ngưỡng</CardTitle>
          <div className="flex items-center gap-2">
            {isConnected ? (
              <span className="flex items-center gap-1 text-xs text-green-600">
                <span className="h-2 w-2 rounded-full bg-green-600" />
                Online
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-red-600">
                <span className="h-2 w-2 rounded-full bg-red-600" />
                Offline
              </span>
            )}
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </div>
        {deviceName && (
          <p className="text-xs text-muted-foreground mt-1">
            Đang hiển thị: <span className="font-medium text-foreground">{deviceName}</span>
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {enabled && isOverThreshold && (
          <Alert variant="destructive">
            <Icons.warning className="h-4 w-4" />
            <AlertDescription>Dòng điện đã vượt ngưỡng {threshold} A!</AlertDescription>
          </Alert>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Dòng hiện tại</span>
            <span className="font-semibold">{currentAmps.toFixed(2)} A</span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full transition-all ${percentage >= 100 ? "bg-red-500" : percentage >= 80 ? "bg-yellow-500" : "bg-blue-500"
                }`}
              style={{ width: `${Math.min(percentage, 100)}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Ngưỡng cảnh báo</span>
            <span className="font-semibold">{threshold} A</span>
          </div>
        </div>

        {isEditing ? (
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="threshold">Ngưỡng cảnh báo (A)</Label>
              <Input
                id="threshold"
                type="number"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                placeholder="0.5"
                min="0"
                step="0.01"
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleSaveThreshold}
                disabled={!isConnected}
              >
                <Icons.success className="mr-2 h-4 w-4" />
                Lưu
              </Button>
              <Button size="sm" variant="outline" onClick={() => setIsEditing(false)}>
                Hủy
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="outline" size="sm" className="w-full bg-transparent" onClick={() => setIsEditing(true)}>
            <Icons.edit className="mr-2 h-4 w-4" />
            Chỉnh sửa ngưỡng
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
