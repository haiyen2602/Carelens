"use client";

// Bac si xin bo sung mot thuoc chua co trong danh muc (FB-14).
//
// Mo tu o goi y thuoc khi go mai khong ra ket qua nao. Truoc day cho do bac
// si cu go tay roi ke luon - chinh la lo hong FB-14. Gio danh muc dong lai,
// nen phai co duong di tiep, neu khong bac si ket han.

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { HoverSelect } from "@/components/hover-select";
import { createDrugRequest } from "@/lib/drug-requests";
import { useAuth } from "@/lib/auth";

// Khop gia tri trong danh muc that (cot `duong_dung` cua bang `drug`).
const DUONG_DUNG_OPTIONS = ["Uống", "Tiêm", "Bôi ngoài da", "Nhỏ mắt", "Xịt mũi", "Đặt", "Khác"];

export function DrugRequestDialog({
  open,
  onOpenChange,
  tenThuocGoiY = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Chu bac si vua go o o tim thuoc - dien san de khong phai go lai. */
  tenThuocGoiY?: string;
}) {
  const { accessToken } = useAuth();
  const [tenThuoc, setTenThuoc] = useState(tenThuocGoiY);
  const [dangThuoc, setDangThuoc] = useState("");
  const [duongDung, setDuongDung] = useState("Uống");
  const [hamLuong, setHamLuong] = useState("");
  const [lyDo, setLyDo] = useState("");
  const [dangGui, setDangGui] = useState(false);

  const coTheGui =
    tenThuoc.trim().length > 0 && dangThuoc.trim().length > 0 && duongDung.length > 0 && !dangGui;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setDangGui(true);
    try {
      await createDrugRequest({ tenThuoc, dangThuoc, duongDung, hamLuong, lyDo }, accessToken);
      toast.success("Đã gửi yêu cầu. Thuốc dùng được sau khi quản trị viên duyệt.");
      onOpenChange(false);
      setDangThuoc("");
      setHamLuong("");
      setLyDo("");
    } catch (err) {
      // Giu nguyen cau cua backend: truong hop chat bi kiem soat, cau do noi
      // ro vuong o hoat chat nao thay vi mot loi chung chung.
      toast.error(err instanceof Error ? err.message : "Không gửi được yêu cầu");
    } finally {
      setDangGui(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Yêu cầu bổ sung thuốc</DialogTitle>
            <DialogDescription>
              Thuốc sẽ kê được sau khi quản trị viên duyệt. Bạn theo dõi trạng thái ở mục Yêu cầu
              của tôi.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="dr-ten">Tên thuốc</Label>
              <Input
                id="dr-ten"
                value={tenThuoc}
                onChange={(e) => setTenThuoc(e.target.value)}
                placeholder="vd. Amlodipine 5mg"
                autoComplete="off"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="dr-dang">Dạng bào chế</Label>
                <Input
                  id="dr-dang"
                  value={dangThuoc}
                  onChange={(e) => setDangThuoc(e.target.value)}
                  placeholder="vd. Viên nén bao phim"
                  autoComplete="off"
                />
                {/* Bat buoc, khong phai thu tuc: day la dau vao quyet dinh
                    lieu thuoc co xac minh duoc bang anh hay khong. */}
                <p className="text-xs text-muted-foreground">
                  Bắt buộc — quyết định liều này có xác minh được bằng ảnh hay không.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dr-duong">Đường dùng</Label>
                <HoverSelect
                  id="dr-duong"
                  value={duongDung}
                  onChange={setDuongDung}
                  options={DUONG_DUNG_OPTIONS.map((o) => ({ value: o, label: o }))}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dr-ham">Hàm lượng (không bắt buộc)</Label>
              <Input
                id="dr-ham"
                value={hamLuong}
                onChange={(e) => setHamLuong(e.target.value)}
                placeholder="vd. 5mg"
                autoComplete="off"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="dr-lydo">Lý do cần bổ sung (không bắt buộc)</Label>
              <Textarea
                id="dr-lydo"
                value={lyDo}
                onChange={(e) => setLyDo(e.target.value)}
                placeholder="Giúp quản trị viên duyệt nhanh hơn."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={!coTheGui}>
              {dangGui ? "Đang gửi…" : "Gửi yêu cầu"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
