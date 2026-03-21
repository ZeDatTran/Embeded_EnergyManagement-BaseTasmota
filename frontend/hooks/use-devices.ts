import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchDevices, controlDevice, fetchDeviceById, fetchDeviceHistory } from "@/lib/api-client"
import type { Device as BackendDevice } from "@/lib/api-client"
import type { DeviceHistoryFetchOptions } from "@/lib/api-client"

// Extended device interface with UI-specific fields
export interface Device extends BackendDevice {
  name?: string
  areaId?: string
  groupId?: string
  status?: "online" | "offline"
  power?: number
  lastUpdate?: string
}

export interface DeviceHistoryPoint {
  timestamp: string
  power: number
  voltage: number
  current: number
  energy: number
}

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    queryFn: async () => {
      const backendDevices = await fetchDevices()
      // Map backend data to Device interface
      return backendDevices.map((device, index) => {
        // Lấy metadata nếu có (từ backend mới)
        const metadata = (device as any).metadata || {}
        const deviceName = metadata.name || device.name || `CB ${index + 1}`
        const deviceLocation = metadata.location || device.location || "N/A"
        
        return {
          id: device.id,
          type: metadata.type || device.type || "cb",
          location: deviceLocation,
          attributes: device.attributes,
          telemetry: device.telemetry,
          // Add UI-specific fields
          name: deviceName,
          areaId: deviceLocation,
          groupId: "",
          status: device.attributes?.POWER === "ON" ? "online" : "offline",
          power: device.attributes?.POWER === "ON" ? 1 : 0,
          lastUpdate: new Date().toISOString(),
          // CB specific fields
          roomType: metadata.room_type,
          roomName: metadata.room_name,
          maxLoad: metadata.max_load,
        } as Device
      })
    },
    refetchInterval: 5000, // Auto refetch every 5s for realtime
  })
}

export function useDevice(deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId],
    queryFn: async () => {
      const device = await fetchDeviceById(deviceId)
      if (!device) return null
      
      // Lấy metadata nếu có (từ backend mới)
      const metadata = (device as any).metadata || {}
      const deviceName = metadata.name || device.name || device.type || "CB"
      const deviceLocation = metadata.location || device.location || "N/A"
      
      return {
        ...device,
        name: deviceName,
        location: deviceLocation,
        type: metadata.type || device.type || "cb",
        status: device.attributes?.POWER === "ON" ? "online" : "offline",
        power: device.attributes?.POWER === "ON" ? 1 : 0,
        lastUpdate: new Date().toISOString(),
        // CB specific fields
        roomType: metadata.room_type,
        roomName: metadata.room_name,
        maxLoad: metadata.max_load,
      } as Device
    },
    enabled: !!deviceId,
    refetchInterval: 3000, // Refetch every 3 seconds for real-time updates
  })
}

export function useDeviceHistory(
  deviceId: string,
  period: string = "day",
  options?: DeviceHistoryFetchOptions
) {
  const normalizedPeriod = (period || "day").toLowerCase()

  return useQuery({
    queryKey: ["device", deviceId, "history", period],
    queryFn: async () => {
      return fetchDeviceHistory(deviceId, normalizedPeriod, options)
    },
    enabled: !!deviceId,
    refetchInterval: normalizedPeriod === "all" ? false : 30000, // Avoid heavy auto-refresh for full history
  })
}

export function useDeviceTree() {
  return useQuery({
    queryKey: ["devices", "tree"],
    queryFn: async () => {
      const devices = await fetchDevices()
      // Group devices by location for tree structure
      const grouped = devices.reduce(
        (acc, device) => {
          const location = device.location || "Unknown"
          if (!acc[location]) {
            acc[location] = []
          }
          acc[location].push(device)
          return acc
        },
        {} as Record<string, BackendDevice[]>
      )

      // Convert to tree format
      return Object.entries(grouped).map(([location, devices]) => ({
        id: location,
        name: location,
        children: devices.map((device) => ({
          id: device.id,
          name: device.type,
        })),
      }))
    },
  })
}

export function useUpdateDevice() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { id: string; power: number }) => {
      const command = data.power === 0 ? "off" : "on"
      return controlDevice(data.id, command as "on" | "off")
    },
    onSuccess: () => {
      // Invalidate the devices query to refetch updated data
      queryClient.invalidateQueries({ queryKey: ["devices"] })
    },
  })
}
