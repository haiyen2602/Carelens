"use client";

import { HelpCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type HuongDan = {
  title: string;
  intro?: string;
  steps: string[];
};

// Khoa theo duong dan, khong theo tieu de trang: tieu de co the doi vi ly do
// hien thi, con duong dan la thu dinh danh trang that su.
//
// `/doctor` phai la khoa CHINH XAC (xem timHuongDan) - moi trang bac si deu
// bat dau bang tien to nay nen so khop tien to se tra ve huong dan trang chu
// cho tat ca.
const HUONG_DAN: Record<string, HuongDan> = {
  "/doctor": {
    title: "Trang chủ",
    intro: "Ảnh chụp nhanh tình hình các bệnh nhân bạn đang theo dõi.",
    steps: [
      "Các thẻ số liệu ở đầu trang tổng hợp mức tuân thủ và số cảnh báo chưa xử lý.",
      "Bấm vào một bệnh nhân để mở nhanh hồ sơ của họ.",
      "Chuông ở góc phải gộp cả cảnh báo lâm sàng lẫn hoạt động gần đây của bạn.",
    ],
  },
  "/doctor/patients": {
    title: "Quản lý bệnh nhân",
    intro: "Nơi xem hồ sơ, phác đồ và mức tuân thủ của từng người.",
    steps: [
      "Gõ tên hoặc mã bệnh nhân vào ô tìm kiếm — không cần gõ dấu.",
      "Bấm “Theo dõi” để nhận cảnh báo của người đó ở Hộp cảnh báo. Không bật thì bạn sẽ không thấy cảnh báo của họ.",
      "Mở một bệnh nhân để xem 3 tab: tình trạng sức khoẻ, phác đồ và mức tuân thủ.",
      "Mọi thay đổi hồ sơ đều được ghi vào trang Lịch sử.",
    ],
  },
  "/doctor/prescribe": {
    title: "Kê đơn thuốc",
    intro: "Tạo phác đồ mới cho một bệnh nhân.",
    steps: [
      "Chọn bệnh nhân, rồi thêm từng thuốc kèm liều và giờ uống.",
      "Nhiều thuốc cùng một giờ sẽ được gộp chung một lượt nhắc.",
      "Bấm xác nhận là đơn được duyệt ngay — bạn vừa kê vừa là người duyệt.",
      "Sau khi duyệt, hệ thống tự sinh lịch nhắc uống cho bệnh nhân.",
    ],
  },
  "/doctor/drugs": {
    title: "Tra cứu thuốc",
    intro: "Tìm thông tin thuốc trong kho dữ liệu của hệ thống.",
    steps: [
      "Tìm theo tên thương mại hoặc hoạt chất.",
      "Dùng các bộ lọc để thu hẹp theo dạng bào chế hoặc nhóm thuốc.",
      "Thông tin ở đây là tài liệu tham khảo, không thay thế quyết định lâm sàng của bạn.",
    ],
  },
  "/doctor/alerts": {
    title: "Hộp cảnh báo",
    intro: "Các sự cố cần bạn xem: bỏ liều, triệu chứng bất thường, dấu hiệu nguy hiểm.",
    steps: [
      "Bạn chỉ thấy cảnh báo của bệnh nhân đang “Theo dõi”.",
      "Bốn bộ lọc (tìm kiếm, mức độ, trạng thái, khoảng ngày) áp dụng đồng thời với nhau.",
      "Bấm một cảnh báo để xem hồ sơ bệnh nhân và người thân ngay trong cửa sổ.",
      "Ba nút xử lý đều hỏi xác nhận trước, và có nút “Hoàn tác” trong 8 giây sau khi lưu.",
    ],
  },
  "/doctor/family": {
    title: "Danh sách người thân",
    intro: "Người nhà đang theo dõi từng bệnh nhân.",
    steps: [
      "Tìm theo tên hoặc mã bệnh nhân để xem ai là người liên hệ của họ.",
      "Hệ thống chỉ lưu email của người thân, chưa có số điện thoại.",
      "Thanh chuyển trang luôn nằm ở đáy màn hình khi bạn cuộn.",
    ],
  },
  "/doctor/audit": {
    title: "Lịch sử",
    intro: "Hai loại bản ghi khác nhau, tách thành hai tab.",
    steps: [
      "“Thao tác của tôi”: những việc chính bạn đã làm — kê đơn, duyệt, xử lý cảnh báo, sửa hồ sơ. Chỉ bạn thấy được của mình.",
      "“Hội thoại AI”: câu bệnh nhân hỏi trợ lý và câu trợ lý đã trả lời, dùng để đối chiếu khi cần.",
      "Cả hai tab đều tìm kiếm được theo tên bệnh nhân hoặc nội dung.",
    ],
  },
  "/doctor/reports/adherence": {
    title: "Tổng quan thông tin",
    intro: "Báo cáo mức tuân thủ uống thuốc theo thời gian.",
    steps: [
      "Chọn khoảng ngày ở góc phải — MỌI số liệu trên trang đều thuộc đúng kỳ đó, kể cả các thẻ ở đầu trang.",
      "Tỉ lệ tuân thủ tính trên các liều đã đến hạn — liều chưa tới giờ không bị tính là bỏ lỡ.",
      "“Chưa có dữ liệu” là bệnh nhân không có liều nào đến hạn trong kỳ, không phải tuân thủ 0%.",
      "Khi cả kỳ có quá ít liều, trang hiện số lượt thay vì phần trăm — tỉ lệ trên mẫu nhỏ dễ gây hiểu nhầm.",
    ],
  },
  "/doctor/profile": {
    title: "Hồ sơ cá nhân",
    steps: ["Cập nhật tên hiển thị và thông tin liên hệ của bạn.", "Đổi mật khẩu tại đây."],
  },
  "/doctor/settings": {
    title: "Cài đặt",
    steps: ["Tuỳ chỉnh giao diện và các lựa chọn hiển thị của tài khoản."],
  },
};

const MAC_DINH: HuongDan = {
  title: "Hướng dẫn sử dụng",
  intro: "Chưa có hướng dẫn riêng cho trang này.",
  steps: [
    "Dùng thanh điều hướng bên trái để chuyển giữa các khu vực.",
    "Chuông ở góc phải gộp cảnh báo lâm sàng và hoạt động gần đây.",
  ],
};

function timHuongDan(pathname: string): HuongDan {
  if (HUONG_DAN[pathname]) return HUONG_DAN[pathname];
  // Trang con (vd /doctor/patients/<id>) dung huong dan cua trang cha - lay
  // khoa DAI NHAT khop de /doctor/reports/adherence khong bi /doctor nuot.
  const khop = Object.keys(HUONG_DAN)
    .filter((key) => key !== "/doctor" && pathname.startsWith(`${key}/`))
    .sort((a, b) => b.length - a.length)[0];
  return khop ? HUONG_DAN[khop] : MAC_DINH;
}

/** Nut "?" tren thanh dau trang: re chuot hien tooltip, bam mo huong dan cua
 * DUNG trang dang xem.
 *
 * Tooltip mot minh khong du cho "huong dan su dung" - no chi chua duoc mot
 * dong chu, ma thu nguoi dung can la vai buoc lam cu the. Nen tooltip chi lam
 * nhiem vu noi cho biet nut nay la gi, con noi dung that nam trong popover. */
export function HelpGuideButton() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const huongDan = timHuongDan(pathname);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                aria-label="Hướng dẫn sử dụng trang này"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted data-[state=open]:bg-muted data-[state=open]:text-foreground"
              >
                <HelpCircle className="h-[18px] w-[18px]" />
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          {/* An tooltip khi popover dang mo - hai lop noi chong len nhau vua
              che mat noi dung vua nhin nhu loi hien thi. */}
          {!open && <TooltipContent side="bottom">Hướng dẫn sử dụng</TooltipContent>}
        </Tooltip>
      </TooltipProvider>

      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-bold">{huongDan.title}</p>
          {huongDan.intro && (
            <p className="mt-0.5 text-xs text-muted-foreground">{huongDan.intro}</p>
          )}
        </div>
        <ul className="max-h-80 space-y-3 overflow-y-auto px-4 py-3">
          {huongDan.steps.map((step, i) => (
            <li key={step} className="flex gap-3 text-sm">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                {i + 1}
              </span>
              <span className="min-w-0 text-muted-foreground">{step}</span>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
