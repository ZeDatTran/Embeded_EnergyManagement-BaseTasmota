"use client"

import { DeviceTable } from "@/components/device-table"

export default function MonitorPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Giám sát CB</h1>
        <p className="text-muted-foreground">Theo dõi và quản lý CB tổng theo thời gian thực</p>
      </div>
      <DeviceTable />
    </div>
  )
}
