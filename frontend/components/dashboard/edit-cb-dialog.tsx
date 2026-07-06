"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { Icons } from "@/components/icons";
import {
  updateCircuitBreaker,
  type CircuitBreakerInput,
  type Device,
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

interface EditCBDialogProps {
  device: Device;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

export function EditCBDialog({
  device,
  open,
  onOpenChange,
  onSuccess,
}: EditCBDialogProps) {
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  // Form state - pre-filled with current device info
  const [name, setName] = useState(device.name || "");
  const [roomType, setRoomType] = useState(
    device.roomType || ""
  );
  const [customRoomName, setCustomRoomName] = useState(
    device.roomName || ""
  );
  const [floor, setFloor] = useState<string>(
    device.floor ? String(device.floor) : ""
  );
  const [maxLoad, setMaxLoad] = useState<string>(
    String(device.maxLoad || 32)
  );

  // Reset form when device changes or dialog opens
  useEffect(() => {
    if (open) {
      setName(device.name || "");
      setRoomType(device.roomType || "");
      setCustomRoomName(device.roomName || "");
      setFloor(device.floor ? String(device.floor) : "");
      setMaxLoad(String(device.maxLoad || 32));
    }
  }, [open, device]);

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

    setLoading(true);

    try {
      const cbData: CircuitBreakerInput = {
        name: name.trim(),
        roomType: roomType || "custom",
        roomName: customRoomName.trim() || ROOM_TYPES.find((r) => r.value === roomType)?.label || name.trim(),
        deviceId: device.id,
        floor: floor ? parseInt(floor, 10) : undefined,
        maxLoad: maxLoad ? parseFloat(maxLoad) : 32,
      };

      const result = await updateCircuitBreaker(device.id, cbData);

      if (result.success) {
        toast({
          title: "Thành công",
          description: `Đã cập nhật CB "${name}"`,
        });
        onOpenChange(false);
        onSuccess?.();
      } else {
        toast({
          title: "Lỗi",
          description: result.message || "Không thể cập nhật CB",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Error updating CB:", error);
      toast({
        title: "Lỗi",
        description: "Có lỗi xảy ra khi cập nhật CB",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icons.edit className="h-5 w-5" />
            Chỉnh sửa CB
          </DialogTitle>
          <DialogDescription>
            Cập nhật thông tin CB: {device.name || device.id.substring(0, 8)}...
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Device Info (Read-only) */}
          <div className="space-y-2">
            <Label className="text-muted-foreground">Thiết bị</Label>
            <div className="px-3 py-2 bg-muted rounded-md text-sm">
              <div className="font-medium">{device.name || "Không rõ"}</div>
              <div className="text-xs text-muted-foreground">ID: {device.id}</div>
            </div>
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
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Hủy
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  Đang lưu...
                </>
              ) : (
                "Lưu thay đổi"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
