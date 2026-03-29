"use client"

import { useEffect, useState } from "react"
import { Loader2, Zap, AlertCircle, CheckCircle2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const API_URL = "http://localhost:5000"

interface PlugForecast {
  plugName: string
  deviceId: string
  status: "success" | "error" | "warning" | "pending"
  predictedBillVnd?: number
  totalKwhForecasted?: number
  totalKwhMonth?: number
  consumedThisMonthKwh?: number
  hourlyPredictions?: any[]
  message?: string
}

interface ForecastResponse {
  status: string
  byPlug?: Record<string, PlugForecast>
  summary?: {
    totalPredictedBillVnd: number
    totalKwhForecasted: number
    totalKwhMonth: number
  }
  pushErrors?: any[]
}

export function PlugForecastRunner() {
  const [isRunning, setIsRunning] = useState(false)
  const [forecasts, setForecasts] = useState<Record<string, PlugForecast>>({})
  const [summary, setSummary] = useState<any>(null)
  const [status, setStatus] = useState<string>("")
  const [pushErrors, setPushErrors] = useState<any[]>([])

  const handleRunAllPlugsForecasts = async () => {
    setIsRunning(true)
    setStatus("Đang tính toán dự báo cho từng plug...")
    setForecasts({})
    setSummary(null)
    setPushErrors([])

    try {
      const res = await fetch(`${API_URL}/forecast/by-plug`)
      const data: ForecastResponse = await res.json()

      if (res.ok && data.status === "success") {
        setForecasts(data.byPlug || {})
        setSummary(data.summary)
        setPushErrors(data.pushErrors || [])
        setStatus("✓ Dự báo hoàn tất! Kết quả đã gửi sang CoreIoT.")
      } else if (data.status === "empty") {
        setStatus("Chưa có plug nào được cấu hình. Vui lòng thêm CB device ở Dashboard trước.")
      } else {
        setStatus(`Lỗi: ${data.status}`)
      }
    } catch (error) {
      setStatus("Lỗi kết nối tới server AI!")
      console.error("Error running plug forecasts:", error)
    } finally {
      setIsRunning(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount)
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "success":
        return "bg-green-50 border-green-200"
      case "error":
        return "bg-red-50 border-red-200"
      case "warning":
        return "bg-yellow-50 border-yellow-200"
      default:
        return "bg-gray-50 border-gray-200"
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success":
        return <CheckCircle2 className="w-5 h-5 text-green-600" />
      case "error":
        return <AlertCircle className="w-5 h-5 text-red-600" />
      case "warning":
        return <AlertCircle className="w-5 h-5 text-yellow-600" />
      default:
        return null
    }
  }

  return (
    <div className="space-y-6">
      {/* Header & Button */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-start">
            <div>
              <CardTitle>Dự báo tiêu thụ từng plug</CardTitle>
              <p className="text-sm text-muted-foreground mt-2">
                Chạy dự báo ML riêng cho từng plug/CB được cấu hình. Kết quả sẽ tự động gửi sang CoreIoT.
              </p>
            </div>
            <button
              onClick={handleRunAllPlugsForecasts}
              disabled={isRunning}
              className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
            >
              {isRunning ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Đang xử lý...
                </>
              ) : (
                <>
                  <Zap className="mr-2 h-4 w-4" />
                  Chạy Dự Báo Ngay
                </>
              )}
            </button>
          </div>
        </CardHeader>
      </Card>

      {/* Status Message */}
      {status && (
        <div className={`p-3 rounded-lg border text-sm ${status.includes("✓") ? "bg-green-50 border-green-200 text-green-800" : "bg-blue-50 border-blue-200 text-blue-800"}`}>
          {status}
        </div>
      )}

      {/* Error Summary */}
      {pushErrors.length > 0 && (
        <Alert className="border-red-200 bg-red-50">
          <AlertCircle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-800">
            {pushErrors.length} plug(s) không thể gửi sang CoreIoT. Kiểm tra logs để biết chi tiết.
          </AlertDescription>
        </Alert>
      )}

      {/* Summary Stats */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <p className="text-sm font-medium text-muted-foreground">Tổng tiền điện dự kiến</p>
                <p className="text-2xl font-bold text-green-600">{formatCurrency(summary.totalPredictedBillVnd)}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <p className="text-sm font-medium text-muted-foreground">Tổng kWh dự báo</p>
                <p className="text-2xl font-bold text-blue-600">{summary.totalKwhForecasted.toFixed(2)} kWh</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-center space-y-2">
                <p className="text-sm font-medium text-muted-foreground">Tổng cả tháng</p>
                <p className="text-2xl font-bold text-orange-600">{summary.totalKwhMonth.toFixed(2)} kWh</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Plug Forecasts Grid */}
      {Object.keys(forecasts).length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-4">Kết quả dự báo từng plug:</h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Object.entries(forecasts).map(([deviceId, forecast]) => (
              <Card key={deviceId} className={`border-2 ${getStatusColor(forecast.status)}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{forecast.plugName}</CardTitle>
                      <p className="text-xs text-muted-foreground mt-1">{deviceId}</p>
                    </div>
                    {getStatusIcon(forecast.status)}
                  </div>
                </CardHeader>

                <CardContent className="space-y-3">
                  {forecast.status === "success" && (
                    <>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Tiền dự kiến:</span>
                          <span className="font-semibold text-green-600">
                            {formatCurrency(forecast.predictedBillVnd || 0)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Đã tiêu thụ:</span>
                          <span className="font-medium">{(forecast.consumedThisMonthKwh || 0).toFixed(2)} kWh</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Dự báo thêm:</span>
                          <span className="font-medium text-blue-600">
                            {(forecast.totalKwhForecasted || 0).toFixed(2)} kWh
                          </span>
                        </div>
                        <div className="flex justify-between border-t pt-2">
                          <span className="text-muted-foreground font-medium">Tổng tháng:</span>
                          <span className="font-bold text-orange-600">
                            {(forecast.totalKwhMonth || 0).toFixed(2)} kWh
                          </span>
                        </div>
                      </div>
                      <div className="text-xs text-green-700 bg-green-50 p-2 rounded">
                        ✓ Dữ liệu đã gửi sang CoreIoT
                      </div>
                    </>
                  )}

                  {forecast.status === "error" && (
                    <div className="text-sm text-red-700">
                      <p className="font-medium">Lỗi: {forecast.message}</p>
                    </div>
                  )}

                  {forecast.status === "warning" && (
                    <div className="text-sm text-yellow-700">
                      <p className="font-medium">⚠ {forecast.message}</p>
                      <p className="text-xs mt-1">Có thể plug này chưa có dữ liệu tiêu thụ hoặc chưa được cấu hình đủ.</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isRunning && Object.keys(forecasts).length === 0 && status && status.includes("empty") && (
        <Card className="border-dashed">
          <CardContent className="pt-6 text-center py-12">
            <AlertCircle className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">Chưa có plug nào được cấu hình</p>
            <p className="text-xs text-muted-foreground mt-2">
              Vui lòng thêm Circuit Breaker (CB) ở trang Dashboard để bắt đầu dự báo.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
