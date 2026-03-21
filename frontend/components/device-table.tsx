"use client"

import { useDevices, useUpdateDevice } from "@/hooks/use-devices"
import { useUIStore } from "@/lib/store"
import { Power, Eye, CircuitBoard } from "lucide-react"
import { useState } from "react"
import Link from "next/link"

export function DeviceTable() {
  const { data: devices, isLoading } = useDevices()
  const { mutate: updateDevice, isPending } = useUpdateDevice()
  const { selectedAreaId } = useUIStore()
  const [updatingId, setUpdatingId] = useState<string | null>(null)

  const filteredDevices = devices?.filter((device) => !selectedAreaId || device.areaId === selectedAreaId) || []

  const handleTogglePower = (deviceId: string, isCurrentlyOn: boolean) => {
    setUpdatingId(deviceId)
    updateDevice(
      { id: deviceId, power: isCurrentlyOn ? 0 : 1 },
      {
        onSettled: () => setUpdatingId(null),
      }
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Tên CB</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Vị trí</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Trạng thái</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Công suất (W)</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Điện áp (V)</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Dòng điện (A)</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900 dark:text-gray-100">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                  Đang tải danh sách CB...
                </td>
              </tr>
            ) : filteredDevices.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                  Không tìm thấy CB nào
                </td>
              </tr>
            ) : (
              filteredDevices.map((device) => (
                <tr key={device.id} className="border-b border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900 dark:text-gray-100">
                    <Link 
                      href={`/monitor/${device.id}`}
                      className="hover:text-blue-600 dark:hover:text-blue-400 hover:underline flex items-center gap-2"
                    >
                      <CircuitBoard size={16} className="text-blue-500" />
                      {device.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">{device.location}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        device.attributes?.POWER === "ON" 
                          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" 
                          : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                      }`}
                    >
                      {device.attributes?.POWER === "ON" ? "Online" : "Offline"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                    {device.telemetry?.["ENERGY-Power"] || "N/A"}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                    {device.telemetry?.["ENERGY-Voltage"] || "N/A"}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                    {device.telemetry?.["ENERGY-Current"] || "N/A"}
                  </td>
                  <td className="px-6 py-4 text-sm flex gap-2">
                    <Link
                      href={`/monitor/${device.id}`}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg font-medium transition-colors bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500"
                    >
                      <Eye size={16} />
                      Chi tiết
                    </Link>
                    <button
                      onClick={() => handleTogglePower(device.id, device.attributes?.POWER === "ON")}
                      disabled={updatingId === device.id || isPending}
                      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 ${
                        device.attributes?.POWER === "ON"
                          ? "bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-200"
                          : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-600 dark:text-gray-200"
                      }`}
                    >
                      <Power size={16} />
                      {device.attributes?.POWER === "ON" ? "On" : "Off"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
