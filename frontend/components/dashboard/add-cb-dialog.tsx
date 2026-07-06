"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Icons } from "@/components/icons";
import {
  addCircuitBreaker,
  fetchAvailableDevices,
  type CircuitBreakerInput,
  type AvailableDevice,
} from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// Danh sách loại phòng có sẵn
const ROOM_TYPES = [
  { value: "living_room", label: "Phòng khách", icon: "living_room" },
  { value: "bedroom", label: "Phòng ngủ", icon: "bedroom" },
  { value: "office", label: "Phòng làm việc", icon: "office" },
  { value: "kitchen", label: "Nhà bếp", icon: "kitchen" },
  { value: "bathroom", label: "Phòng tắm", icon: "bathroom" },
  { value: "balcony", label: "Ban công", icon: "balcony" },
] as const;

interface AddCBDialogProps {
  onSuccess?: () => void;
}

export function AddCBDialog({ onSuccess }: AddCBDialogProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const { toast } = useToast();

  // Available devices from CoreIoT
  const [availableDevices, setAvailableDevices] = useState<AvailableDevice[]>([]);

  // Form state
  const [name, setName] = useState("");
  const [roomType, setRoomType] = useState<string>("");
  const [customRoomName, setCustomRoomName] = useState("");
  const [floor, setFloor] = useState<string>("");
  const [maxLoad, setMaxLoad] = useState<string>("32");
  const [deviceId, setDeviceId] = useState("");
  const [manualInput, setManualInput] = useState(false);

  // Load available devices when dialog opens
  useEffect(() => {
    if (open) {
      loadAvailableDevices();
    }
  }, [open]);

  const loadAvailableDevices = async () => {
    setLoadingDevices(true);
    try {
      const devices = await fetchAvailableDevices();
      setAvailableDevices(devices);
    } catch (error) {
      console.error("Error loading devices:", error);
    } finally {
      setLoadingDevices(false);
    }
  };

  const resetForm = () => {
    setName("");
    setRoomType("");
    setCustomRoomName("");
    setFloor("");
    setMaxLoad("32");
    setDeviceId("");
    setManualInput(false);
  };

  // Auto-fill name when device is selected
  const handleDeviceSelect = (selectedDeviceId: string) => {
    setDeviceId(selectedDeviceId);
    const device = availableDevices.find((d) => d.id === selectedDeviceId);
    if (device && !name) {
      setName(`CB ${device.name}`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast({
        title: "Lỗi",
        description: "Vui lòng nhập tên CB",
        variant: "destructive",
      });
      return;
    }

    if (!roomType && !customRoomName.trim()) {
      toast({
        title: "Lỗi",
        description: "Vui lòng chọn loại phòng hoặc nhập tên phòng tùy chỉnh",
        variant: "destructive",
      });
      return;
    }

    if (!deviceId.trim()) {
      toast({
        title: "Lỗi",
        description: "Vui lòng chọn thiết bị hoặc nhập Device ID",
        variant: "destructive",
      });
      return;
    }

    setLoading(true);

    try {
      const cbData: CircuitBreakerInput = {
        name: name.trim(),
        roomType: roomType || "custom",
        roomName: customRoomName.trim() || ROOM_TYPES.find((r) => r.value === roomType)?.label || name.trim(),
        deviceId: deviceId.trim(),
        floor: floor ? parseInt(floor, 10) : undefined,
        maxLoad: maxLoad ? parseFloat(maxLoad) : 32,
      };

      const result = await addCircuitBreaker(cbData);

      if (result.success) {
        toast({
          title: "Thành công",
          description: `Đã thêm CB "${name}" cho ${cbData.roomName}`,
        });
        resetForm();
        setOpen(false);
        onSuccess?.();
      } else {
        toast({
          title: "Lỗi",
          description: result.message || "Không thể thêm CB",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Error adding CB:", error);
      toast({
        title: "Lỗi",
        description: "Có lỗi xảy ra khi thêm CB",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Filter devices: unconfigured first, then configured
  const sortedDevices = [...availableDevices].sort((a, b) => {
    if (a.isConfigured === b.isConfigured) return 0;
    return a.isConfigured ? 1 : -1;
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Icons.plus className="mr-2 h-4 w-4" />
          Thêm CB mới
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icons.cb className="h-5 w-5" />
            Thêm CB Tổng Phòng
          </DialogTitle>
          <DialogDescription>
            Chọn thiết bị từ CoreIoT và cấu hình CB cho phòng
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Device Selection */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>
                Chọn thiết bị <span className="text-red-500">*</span>
              </Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setManualInput(!manualInput)}
                className="text-xs h-6"
              >
                {manualInput ? "Chọn từ danh sách" : "Nhập thủ công"}
              </Button>
            </div>

            {manualInput ? (
              <Input
                placeholder="Nhập Device ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
              />
            ) : (
              <Select value={deviceId} onValueChange={handleDeviceSelect}>
                <SelectTrigger>
                  <SelectValue
                    placeholder={
                      loadingDevices
                        ? "Đang tải danh sách..."
                        : "Chọn thiết bị từ CoreIoT"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {loadingDevices ? (
                    <div className="flex items-center justify-center py-4">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                      <span className="ml-2 text-sm">Đang tải...</span>
                    </div>
                  ) : sortedDevices.length === 0 ? (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      Không tìm thấy thiết bị nào
                    </div>
                  ) : (
                    sortedDevices.map((device) => (
                      <SelectItem
                        key={device.id}
                        value={device.id}
                        disabled={device.isConfigured}
                      >
                        <div className="flex items-center gap-2">
                          <div className="flex flex-col">
                            <span className={device.isConfigured ? "text-muted-foreground" : "font-medium"}>
                              {device.name}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              ID: {device.id.substring(0, 12)}...
                            </span>
                          </div>
                          {device.isConfigured && (
                            <Badge variant="secondary" className="text-xs ml-auto">
                              Đã dùng
                            </Badge>
                          )}
                        </div>
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            )}

            {!manualInput && (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={loadAvailableDevices}
                  disabled={loadingDevices}
                  className="text-xs h-6 px-2"
                >
                  <Icons.activity className="mr-1 h-3 w-3" />
                  Làm mới
                </Button>
                <span className="text-xs text-muted-foreground">
                  {availableDevices.filter(d => !d.isConfigured).length}/{availableDevices.length} khả dụng
                </span>
              </div>
            )}
          </div>

          {/* Tên CB */}
          <div className="space-y-2">
            <Label htmlFor="name">
              Tên CB <span className="text-red-500">*</span>
            </Label>
            <Input
              id="name"
              placeholder="VD: CB Phòng khách, CB Tầng 1..."
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Loại phòng */}
          <div className="space-y-2">
            <Label>Loại phòng</Label>
            <Select value={roomType} onValueChange={setRoomType}>
              <SelectTrigger>
                <SelectValue placeholder="Chọn loại phòng..." />
              </SelectTrigger>
              <SelectContent>
                {ROOM_TYPES.map((room) => {
                  const RoomIcon = Icons[room.icon as keyof typeof Icons];
                  return (
                    <SelectItem key={room.value} value={room.value}>
                      <div className="flex items-center gap-2">
                        {RoomIcon && <RoomIcon className="h-4 w-4" />}
                        {room.label}
                      </div>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>

          {/* Tên phòng tùy chỉnh */}
          <div className="space-y-2">
            <Label htmlFor="customRoomName">
              Hoặc nhập tên phòng tùy chỉnh
            </Label>
            <Input
              id="customRoomName"
              placeholder="VD: Phòng khách tầng 2, Phòng ngủ con..."
              value={customRoomName}
              onChange={(e) => setCustomRoomName(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Nếu điền tên tùy chỉnh, sẽ ưu tiên dùng tên này
            </p>
          </div>

          {/* Tầng và Tải tối đa */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="floor">Tầng (tùy chọn)</Label>
              <Input
                id="floor"
                type="number"
                placeholder="VD: 1, 2, 3..."
                value={floor}
                onChange={(e) => setFloor(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxLoad">Tải tối đa (A)</Label>
              <Input
                id="maxLoad"
                type="number"
                placeholder="32"
                value={maxLoad}
                onChange={(e) => setMaxLoad(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              Hủy
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <span className="h-4 w-4 mr-2 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Đang thêm...
                </>
              ) : (
                <>
                  <Icons.plus className="mr-2 h-4 w-4" />
                  Thêm CB
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
