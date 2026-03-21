"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icons } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import type { Device } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DeviceStatusCardProps {
  device: Device
}

export function DeviceStatusCard({ device }: DeviceStatusCardProps) {
  // Lấy icon dựa trên type hoặc roomType, mặc định là cb
  const getDeviceIcon = () => {
    // Nếu có roomType, ưu tiên dùng icon phòng
    if (device.roomType && Icons[device.roomType as keyof typeof Icons]) {
      return Icons[device.roomType as keyof typeof Icons];
    }
    // Nếu type là cb hoặc circuit_breaker
    if (device.type === "cb" || device.type === "circuit_breaker") {
      return Icons.cb;
    }
    // Fallback theo type
    return Icons[device.type as keyof typeof Icons] || Icons.cb;
  };

  const DeviceIcon = getDeviceIcon();

  return (
    <Card className="overflow-hidden hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-lg",
                device.isOn
                  ? "bg-blue-500/20 text-blue-500"
                  : "bg-muted text-muted-foreground"
              )}
            >
              <DeviceIcon className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base">{device.name}</CardTitle>
              <p className="text-xs text-muted-foreground">{device.location}</p>
            </div>
          </div>
          <Badge
            variant={device.status === "online" ? "default" : "secondary"}
            className="text-xs"
          >
            {device.status === "online" ? (
              <Icons.online className="mr-1 h-3 w-3" />
            ) : (
              <Icons.offline className="mr-1 h-3 w-3" />
            )}
            {device.status === "online" ? "Online" : "Offline"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Device metrics */}
        <div className="space-y-2 text-sm">
          {device.voltage !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Điện áp:</span>
              <span className="font-medium">{device.voltage}V</span>
            </div>
          )}
          {device.current !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Dòng điện:</span>
              <span className="font-medium">{device.current.toFixed(3)}A</span>
            </div>
          )}
          {device.power !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Công suất:</span>
              <span className="font-medium">{device.power}W</span>
            </div>
          )}
          {device.powerFactor !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Hệ số công suất:</span>
              <span className="font-medium">{(device.powerFactor * 100).toFixed(1)}%</span>
            </div>
          )}
          {device.energyToday !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Năng lượng hôm nay:</span>
              <span className="font-medium">{device.energyToday.toFixed(3)} kWh</span>
            </div>
          )}
          {device.energyTotal !== undefined && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tổng năng lượng:</span>
              <span className="font-medium">{device.energyTotal.toFixed(3)} kWh</span>
            </div>
          )}
        </div>

        {/* Status badge */}
        <div className="flex items-center justify-between rounded-lg bg-muted/50 p-3">
          <span className="text-sm text-muted-foreground">Trạng thái:</span>
          <Badge
            variant={device.isOn ? "default" : "secondary"}
            className="text-xs"
          >
            {device.isOn ? (
              <>
                <Icons.power className="mr-1 h-3 w-3" />
                Đang bật
              </>
            ) : (
              <>
                <Icons.powerOff className="mr-1 h-3 w-3" />
                Đang tắt
              </>
            )}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
