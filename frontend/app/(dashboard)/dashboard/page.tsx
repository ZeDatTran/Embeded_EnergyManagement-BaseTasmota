"use client";

import { useEffect, useRef, useState } from "react";
import { StatCard } from "@/components/dashboard/stat-card";
import { DeviceStatusCard } from "@/components/dashboard/device-status-card";
import { AddCBDialog } from "@/components/dashboard/add-cb-dialog";
import { Icons } from "@/components/icons";
import { fetchDevices, controlAllDevices, type Device } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { useSocket } from "@/context/SocketContext";

export default function DashboardPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [controlling, setControlling] = useState(false)
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

    // Listen for realtime updates
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

    return () => {
      socket.off("dashboard_update", handleDashboardUpdate);
    };
  }, [socket, isConnected]);

  const handleTurnOnAll = async () => {
    setControlling(true)
    const results = await controlAllDevices("ON")
    if (results.length > 0) {
      setDevices((prevDevices) =>
        prevDevices.map((device) => {
          const result = results.find((r) => r.id === device.id)
          return result ? { ...device, isOn: true } : device
        }),
      )
    }
    setControlling(false)
  }

  const handleTurnOffAll = async () => {
    setControlling(true)
    const results = await controlAllDevices("OFF")
    if (results.length > 0) {
      setDevices((prevDevices) =>
        prevDevices.map((device) => {
          const result = results.find((r) => r.id === device.id)
          return result ? { ...device, isOn: false } : device
        }),
      )
    }
    setControlling(false)
  }

  const onlineDevices = devices.filter((d) => d.status === "online").length;
  const activeDevices = devices.filter((d) => d.isOn).length;
  const totalPower = devices.reduce((sum, d) => sum + (d.power || 0), 0);

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

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm sm:text-base text-muted-foreground">Quản lý CB tổng theo phòng</p>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Tổng CB"
          value={devices.length}
          icon={<Icons.cb className="h-6 w-6 text-blue-500" />}
        />
        <StatCard
          title="Đang hoạt động"
          value={activeDevices}
          icon={<Icons.power className="h-6 w-6 text-green-500" />}
        />
        <StatCard
          title="Đang online"
          value={onlineDevices}
          icon={<Icons.online className="h-6 w-6 text-blue-500" />}
        />
        <StatCard
          title="Tổng công suất"
          value={`${totalPower}W`}
          icon={<Icons.energy className="h-6 w-6 text-yellow-500" />}
        />
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <Button
          onClick={handleTurnOnAll}
          disabled={controlling}
          className="flex-1 bg-green-600 hover:bg-green-700 text-white"
          size="lg"
        >
          <Icons.power className="mr-2 h-5 w-5" />
          {controlling ? "Đang xử lý..." : "Bật tất cả"}
        </Button>
        <Button
          onClick={handleTurnOffAll}
          disabled={controlling}
          className="flex-1 bg-red-600 hover:bg-red-700 text-white"
          variant="default"
          size="lg"
        >
          <Icons.power className="mr-2 h-5 w-5" />
          {controlling ? "Đang xử lý..." : "Tắt tất cả"}
        </Button>
      </div>

      {/* CB overview - now full width */}
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
              Chưa có CB nào. Nhấn "Thêm CB mới" để bắt đầu.
            </div>
          )}
          {devices.map((device) => (
            <DeviceStatusCard
              key={device.id}
              device={device}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
