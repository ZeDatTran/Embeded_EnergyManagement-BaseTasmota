"use client"

import { useEffect, useState } from "react"
import { Loader2, Zap } from "lucide-react"
import { useAuth } from "@/context/AuthContext"

// Định nghĩa kiểu dữ liệu trả về từ Server AI
interface ForecastData {
    tien_can_tra_vnd: number
    tong_kwh_du_doan_duoc: number
    tong_kwh_ca_thang: number
    kwh_da_tieu_thu_thang_nay?: number
}

const AI_SERVER_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000"
const STORAGE_KEY = "ai_forecast_result" // session storage
const FORECAST_TIMEOUT_MS = 90000

export function AIPredictEnergy() {
    const [forecastData, setForecastData] = useState<ForecastData | null>(null)
    const [isForecasting, setIsForecasting] = useState(false)
    const [forecastStatus, setForecastStatus] = useState<string>("")
    const { token } = useAuth()

    // Ưu tiên lấy dữ liệu mới nhất từ server; cache chỉ dùng làm fallback.
    useEffect(() => {
        const loadLatestSummary = async () => {
            try {
                if (!token) return;
                const resSummary = await fetch(`${AI_SERVER_URL}/forecast/summary`, {
                    headers: { "Authorization": `Bearer ${token}` }
                })
                const dataSummary = await resSummary.json()

                if (resSummary.ok && dataSummary.status === "success") {
                    setForecastData(dataSummary.data)
                    setForecastStatus("Dữ liệu mới nhất từ server.")
                    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(dataSummary.data))
                    return
                }
            } catch (e) {
                console.error("Lỗi lấy summary mới nhất", e)
            }

            const saved = sessionStorage.getItem(STORAGE_KEY)
            if (saved) {
                try {
                    setForecastData(JSON.parse(saved))
                    setForecastStatus("Dữ liệu từ lần chạy gần nhất.")
                } catch (e) {
                    console.error("Lỗi đọc cache", e)
                }
            }
        }

        loadLatestSummary()
    }, [token])

    const handleRunForecast = async () => {
        setIsForecasting(true)
        setForecastStatus("Đang gửi dữ liệu sang AI Server...")
        setForecastData(null) // Reset giao diện

        try {
            const controller = new AbortController()
            const timeoutId = setTimeout(() => controller.abort(), FORECAST_TIMEOUT_MS)

            const res = await fetch(`${AI_SERVER_URL}/forecast`, {
                method: "GET",
                headers: { "Authorization": `Bearer ${token}` },
                signal: controller.signal,
            })

            clearTimeout(timeoutId)

            let result: any = null
            try {
                result = await res.json()
            } catch {
                result = null
            }

            if (res.ok) {
                // Lấy lại summary chuẩn
                const resSummary = await fetch(`${AI_SERVER_URL}/forecast/summary`, {
                    headers: { "Authorization": `Bearer ${token}` }
                })
                const dataSummary = await resSummary.json()

                if (dataSummary.status === "success") {
                    setForecastData(dataSummary.data)
                    setForecastStatus("Dự báo thành công!")

                    //Lưu kết quả vào sessionStorage
                    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(dataSummary.data))
                }
            } else {
                const message = result?.message || "Không nhận được phản hồi hợp lệ từ server dự báo."
                setForecastStatus(`Lỗi: ${message}`)
            }
        } catch (error: any) {
            if (error?.name === "AbortError") {
                setForecastStatus("Lỗi: AI Server phản hồi quá chậm (timeout 90s).")
            } else {
                setForecastStatus("Lỗi kết nối tới Server AI!")
            }
        } finally {
            setIsForecasting(false)
        }
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount)
    }

    return (
        <div className="rounded-xl border bg-card text-card-foreground shadow p-6">
            <div className="flex flex-col gap-6">
                {/* Header & Button Section */}
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                    <div>
                        <h3 className="text-lg font-semibold leading-none tracking-tight">Dự báo tiền điện và tiêu thụ</h3>
                        <p className="text-sm text-muted-foreground mt-1">
                            Sử dụng Machine Learning để dự đoán hóa đơn cuối tháng dựa trên thói quen hiện tại.
                        </p>
                    </div>

                    <div className="flex flex-col items-end gap-2">
                        <button
                            onClick={handleRunForecast}
                            disabled={isForecasting}
                            className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
                        >
                            {isForecasting ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Đang tính toán...
                                </>
                            ) : (
                                <>
                                    <Zap className="mr-2 h-4 w-4" />
                                    Chạy Dự Báo Ngay
                                </>
                            )}
                        </button>
                        {forecastStatus && <span className="text-xs text-muted-foreground">{forecastStatus}</span>}
                    </div>
                </div>

                <div className="h-[1px] w-full bg-border" />

                {/* 3 Info Cards Grid */}
                <div className="grid gap-4 md:grid-cols-3">
                    {/* Card 1: Tiền điện */}
                    <div className="rounded-lg border bg-card p-4 shadow-sm flex flex-col items-center justify-center text-center space-y-2">
                        <span className="text-sm font-medium text-muted-foreground">Tiền điện dự kiến</span>
                        <span className="text-2xl font-bold text-green-600">
                            {forecastData ? formatCurrency(forecastData.tien_can_tra_vnd) : "--- ₫"}
                        </span>
                    </div>

                    {/* Card 2: Dự báo thêm */}
                    <div className="rounded-lg border bg-card p-4 shadow-sm flex flex-col items-center justify-center text-center space-y-2">
                        <span className="text-sm font-medium text-muted-foreground">Dự báo thêm (Tương lai)</span>
                        <span className="text-2xl font-bold text-blue-600">
                            {forecastData ? `${forecastData.tong_kwh_du_doan_duoc.toFixed(2)} kWh` : "--- kWh"}
                        </span>
                    </div>

                    {/* Card 3: Tổng tháng */}
                    <div className="rounded-lg border bg-card p-4 shadow-sm flex flex-col items-center justify-center text-center space-y-2">
                        <span className="text-sm font-medium text-muted-foreground">Tổng cả tháng</span>
                        <span className="text-2xl font-bold text-orange-600">
                            {forecastData ? `${forecastData.tong_kwh_ca_thang.toFixed(2)} kWh` : "--- kWh"}
                        </span>
                    </div>
                </div>

                {forecastData && (
                    <div className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
                        Đã tiêu thụ tháng này: {Number(forecastData.kwh_da_tieu_thu_thang_nay || 0).toFixed(2)} kWh | 
                        Dự báo thêm: {forecastData.tong_kwh_du_doan_duoc.toFixed(2)} kWh | 
                        Tổng tháng: {forecastData.tong_kwh_ca_thang.toFixed(2)} kWh
                    </div>
                )}
            </div>
        </div>
    )
}