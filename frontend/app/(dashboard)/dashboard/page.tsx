"use client";

import { useEffect, useRef, useState } from "react";
import { StatCard } from "@/components/dashboard/stat-card";
import { DeviceStatusCard } from "@/components/dashboard/device-status-card";
import { AddCBDialog } from "@/components/dashboard/add-cb-dialog";
import { EmergencyStopButton } from "@/components/dashboard/emergency-stop-button";
import { UpcomingSchedules } from "@/components/dashboard/upcoming-schedules";
import { EnergyTodayCard } from "@/components/dashboard/energy-today-card";
import { Icons } from "@/components/icons";
import { fetchDevices, type Device } from "@/lib/api";
import { useSocket } from "@/context/SocketContext";

export default function DashboardPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const { socket, isConnected } = useSocket();

  const isFetching = useRef(false);

  const loadDevices = async (showLoader = false) => {
    if (isFetching.current) return;
    isFetching.current = true;
    try {
      if (showLoader) setLoading(true);
      const data = await fetchDevices();
      setDevices(data);
    } catch (e) {
      console.error("Error loading devices:", e);
    } finally {
      if (showLoader) setLoading(false);
      isFetching.current = false;
    }
  };

  useEffect(() => {
    loadDevices(true);
  }, []);

  // Socket realtime updates
  useEffect(() => {
    if (!socket || !isConnected) return;

    // Join dashboard room
    socket.emit("join_dashboard");
    console.log("Dashboard: Joined dashboard room");

    const handleDeviceAdded = () => {
      console.log("Device added - refreshing device list");
      loadDevices(false);
    };

    const handleDeviceRemoved = () => {
      console.log("Device removed - refreshing device list");
      loadDevices(false);
    };

    const handleDeviceUpdated = () => {
      console.log("Device updated - refreshing device list");
      loadDevices(false);
    };

    const handleDashboardUpdate = (payload: any) => {
      console.log("Dashboard update received:", payload);

      try {
        // Handle initial snapshot (array of all devices)
        if (payload.data && Array.isArray(payload.data)) {
          const updatedDevices = payload.data.map((item: any) => ({
            id: item.id,
            name: item.name,
            type: item.type,
            location: item.location,
            status: item.attributes?.POWER === "ON" ? "online" : "offline",
            isOn: item.attributes?.POWER === "ON",
            power: parseFloat(item.telemetry?.["ENERGY-Power"] || "0"),
            voltage: parseFloat(item.telemetry?.["ENERGY-Voltage"] || "0"),
            current: parseFloat(item.telemetry?.["ENERGY-Current"] || "0"),
            energyToday: parseFloat(item.telemetry?.["ENERGY-Today"] || "0"),
          }));
          setDevices(updatedDevices);
        }
        // Handle individual device update
        else if (payload.device_id && payload.data) {
          setDevices((prev) =>
            prev.map((device) => {
              if (device.id === payload.device_id) {
                const updates: Partial<Device> = {};

                // Extract telemetry data
                const telemetry = payload.data.telemetry || {};
                if (telemetry["ENERGY-Power"] !== undefined && telemetry["ENERGY-Power"] !== "N/A") {
                  updates.power = parseFloat(telemetry["ENERGY-Power"]);
                }
                if (telemetry["ENERGY-Voltage"] !== undefined && telemetry["ENERGY-Voltage"] !== "N/A") {
                  updates.voltage = parseFloat(telemetry["ENERGY-Voltage"]);
                }
                if (telemetry["ENERGY-Current"] !== undefined && telemetry["ENERGY-Current"] !== "N/A") {
                  updates.current = parseFloat(telemetry["ENERGY-Current"]);
                }
                if (telemetry["ENERGY-Today"] !== undefined && telemetry["ENERGY-Today"] !== "N/A") {
                  updates.energyToday = parseFloat(telemetry["ENERGY-Today"]);
                }
                if (telemetry["ENERGY-Total"] !== undefined && telemetry["ENERGY-Total"] !== "N/A") {
                  updates.energyTotal = parseFloat(telemetry["ENERGY-Total"]);
                }
                if (telemetry["ENERGY-Factor"] !== undefined && telemetry["ENERGY-Factor"] !== "N/A") {
                  updates.powerFactor = parseFloat(telemetry["ENERGY-Factor"]);
                }

                // Extract attributes (POWER status)
                const attributes = payload.data.attributes || {};
                if (attributes.POWER !== undefined && attributes.POWER !== "N/A") {
                  updates.isOn = attributes.POWER === "ON";
                  updates.status = updates.isOn ? "online" : "offline";
                }

                // Extract metadata if needed (name, type, location)
                const metadata = payload.data.metadata || {};
                if (metadata.name) updates.name = metadata.name;
                if (metadata.type) updates.type = metadata.type;
                if (metadata.location) updates.location = metadata.location;

                return { ...device, ...updates };
              }
              return device;
            })
          );
        }
      } catch (error) {
        console.error("Error processing dashboard update:", error);
      }
    };

    socket.on("dashboard_update", handleDashboardUpdate);
    socket.on("device_added", handleDeviceAdded);
    socket.on("device_removed", handleDeviceRemoved);
    socket.on("device_updated", handleDeviceUpdated);

    return () => {
      socket.off("dashboard_update", handleDashboardUpdate);
      socket.off("device_added", handleDeviceAdded);
      socket.off("device_removed", handleDeviceRemoved);
      socket.off("device_updated", handleDeviceUpdated);
    };
  }, [socket, isConnected]);

  const onlineDevices = devices.filter((d) => d.status === "online").length;
  const activeDevices = devices.filter((d) => d.isOn).length;
  const totalPower = devices.reduce((sum, d) => sum + (d.power || 0), 0);
  const totalEnergyToday = devices.reduce((sum, d) => sum + (d.energyToday || 0), 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-2">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
          <p className="text-sm text-muted-foreground">Đang tải dữ liệu...</p>
        </div>
      </div>
    );
  }

  // Get current greeting based on time
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Chào buổi sáng ☀️";
    if (hour < 18) return "Chào buổi chiều 🌤️";
    return "Chào buổi tối 🌙";
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            {getGreeting()}
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-1">
            Quản lý và giám sát hệ thống CB tổng theo phòng
          </p>
        </div>

        {/* Emergency Stop Button */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex flex-col items-end mr-2">
            <span className="text-xs font-medium text-red-500/80">Tắt khẩn cấp</span>
            <span className="text-[10px] text-muted-foreground">Ngắt tất cả CB</span>
          </div>
          <EmergencyStopButton onSuccess={() => loadDevices(false)} />
        </div>
      </div>

      {/* Stats grid with gradient backgrounds */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Tổng CB"
          value={devices.length}
          icon={<Icons.cb className="h-6 w-6 text-blue-500" />}
          gradientClass="stat-gradient-blue"
        />
        <StatCard
          title="Đang hoạt động"
          value={activeDevices}
          icon={<Icons.power className="h-6 w-6 text-emerald-500" />}
          gradientClass="stat-gradient-green"
        />
        <StatCard
          title="Đang online"
          value={onlineDevices}
          icon={<Icons.online className="h-6 w-6 text-cyan-500" />}
          gradientClass="stat-gradient-cyan"
        />
        <StatCard
          title="Tổng công suất"
          value={`${totalPower.toFixed(1)}W`}
          icon={<Icons.energy className="h-6 w-6 text-amber-500" />}
          gradientClass="stat-gradient-amber"
        />
      </div>

      {/* Upcoming Schedules + Energy Today */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <UpcomingSchedules />
        </div>
        <div>
          <EnergyTodayCard realtimeEnergyToday={totalEnergyToday} />
        </div>
      </div>

      {/* CB overview - full width */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">CB Tổng theo phòng</h2>
          <div className="flex items-center gap-3">
            <AddCBDialog onSuccess={() => loadDevices(false)} />
            <span className="text-sm text-muted-foreground">
              {devices.length} CB
            </span>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {devices.length === 0 && (
            <div className="col-span-full text-center py-8 text-muted-foreground">
              Chưa có CB nào. Nhấn &quot;Thêm CB mới&quot; để bắt đầu.
            </div>
          )}
          {devices.map((device) => (
            <DeviceStatusCard
              key={device.id}
              device={device}
              onRefresh={() => loadDevices(false)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
