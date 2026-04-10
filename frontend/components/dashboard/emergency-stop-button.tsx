"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { controlAllDevices } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { ShieldOff } from "lucide-react";

interface EmergencyStopButtonProps {
  onSuccess?: () => void;
}

export function EmergencyStopButton({ onSuccess }: EmergencyStopButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [executing, setExecuting] = useState(false);
  const { toast } = useToast();

  const handleEmergencyStop = async () => {
    setExecuting(true);
    try {
      const results = await controlAllDevices("OFF");
      if (results.length > 0) {
        toast({
          title: "Tắt khẩn cấp thành công",
          description: `Đã tắt ${results.length} thiết bị.`,
        });
        onSuccess?.();
      } else {
        toast({
          title: "Không có thiết bị nào được tắt",
          description: "Có thể tất cả thiết bị đã tắt sẵn.",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Emergency stop error:", error);
      toast({
        title: "Lỗi tắt khẩn cấp",
        description: "Không thể tắt thiết bị. Vui lòng thử lại.",
        variant: "destructive",
      });
    } finally {
      setExecuting(false);
      setDialogOpen(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setDialogOpen(true)}
        disabled={executing}
        className="group relative flex items-center justify-center h-14 w-14 rounded-full bg-red-600 hover:bg-red-700 text-white shadow-lg transition-all duration-300 emergency-pulse disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        title="Tắt khẩn cấp tất cả thiết bị"
      >
        {/* Outer ring animation on hover */}
        <span className="absolute inset-0 rounded-full border-2 border-red-400/50 group-hover:animate-ping" />
        
        {/* Icon */}
        <ShieldOff className="h-6 w-6 relative z-10" />
        
        {/* Processing spinner overlay */}
        {executing && (
          <div className="absolute inset-0 flex items-center justify-center rounded-full bg-red-800/80">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-white border-t-transparent" />
          </div>
        )}
      </button>

      <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <ShieldOff className="h-6 w-6 text-red-600 dark:text-red-400" />
              </div>
              <AlertDialogTitle className="text-xl">
                Tắt Khẩn Cấp
              </AlertDialogTitle>
            </div>
            <AlertDialogDescription className="text-base leading-relaxed">
              Bạn có chắc chắn muốn <strong className="text-red-600 dark:text-red-400">tắt toàn bộ thiết bị</strong>?
              Hành động này sẽ ngắt điện tất cả CB đang hoạt động trong hệ thống.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:gap-0">
            <AlertDialogCancel disabled={executing}>
              Hủy bỏ
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleEmergencyStop}
              disabled={executing}
              className="bg-red-600 text-white hover:bg-red-700 focus:ring-red-500"
            >
              {executing ? (
                <span className="flex items-center gap-2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Đang tắt...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <ShieldOff className="h-4 w-4" />
                  Xác nhận tắt tất cả
                </span>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
