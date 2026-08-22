// Toan bo copy tieng Viet cua landing page, tach rieng khoi JSX (giai doan 1
// cua ke hoach redesign) de sau nay them content.en.ts cho i18n ma khong
// phai viet lai component. Doi tuong tiep can: nguoi than 25-40 tuoi, ban
// ron, co cha/me dang dieu tri dai ngay (specs/product-vision.md muc 2.1).
//
// Co tinh khong dua nhieu con so kiem thu/eval vao day (quyet dinh PM
// 2026-08-22) - landing thien ve cam xuc/long tin hon la dashboard so lieu.

export const content = {
  header: {
    logo: "CapyMedi",
    nav: [
      { label: "Tính năng", href: "#capabilities" },
      { label: "Cách hoạt động", href: "#how-it-works" },
      { label: "An toàn", href: "#safety" },
    ],
    login: "Đăng nhập",
    cta: "Đăng ký tài khoản",
  },

  hero: {
    eyebrow: "Nền tảng đồng hành uống thuốc cho gia đình",
    title: "Biết ngay khi người thân quên uống thuốc",
    titleHighlight: "không phải gọi điện nhắc mỗi ngày.",
    subtitle:
      "CapyMedi nhắc lịch, xác nhận từng liều bằng ảnh, và báo cho bạn ngay khi có gì bất thường — để bạn đồng hành cùng người thân, không phải giám sát từng viên thuốc.",
    ctaPrimary: "Đăng ký tài khoản",
    ctaSecondary: "Xem cách hoạt động",
  },

  capabilities: {
    title: "CapyMedi giúp được gì",
    subtitle: "Bốn việc CapyMedi làm thay bạn mỗi ngày.",
    items: [
      {
        title: "Nhắc đúng giờ, đúng liều",
        desc: "Lịch uống thuốc tự sinh từ đơn của bác sĩ, nhắc đúng khung giờ đã chỉ định — không cần ai nhớ hộ.",
      },
      {
        title: "Xác nhận bằng ảnh",
        desc: "Mỗi lần uống thuốc, bệnh nhân chụp ảnh xác nhận; hệ thống đối chiếu đúng loại và số lượng viên.",
      },
      {
        title: "Chatbot tra cứu thuốc có nguồn",
        desc: "Hỏi công dụng, tác dụng phụ, cách dùng — trả lời kèm trích nguồn từ dữ liệu đã thẩm định, không suy diễn khi thiếu dữ liệu.",
      },
      {
        title: "Báo đúng lúc, đúng người",
        desc: "Bỏ lỡ liều hoặc có dấu hiệu bất thường, hệ thống báo ngay cho người thân theo dõi và bác sĩ phụ trách.",
      },
    ],
  },

  howItWorks: {
    title: "Cách hoạt động",
    subtitle: "Bốn bước, từ đơn thuốc của bác sĩ tới xác nhận mỗi ngày.",
    steps: [
      {
        step: "1",
        title: "Bác sĩ kê đơn",
        desc: "Từ danh mục thuốc đã thẩm định. Thuốc ngoài danh mục phải qua admin duyệt riêng trước khi kê được.",
      },
      {
        step: "2",
        title: "Hệ thống sinh lịch",
        desc: "Từ đơn thuốc, CapyMedi tự tạo lịch uống đúng khung giờ, liều lượng.",
      },
      {
        step: "3",
        title: "Bệnh nhân xác nhận",
        desc: "Mỗi lần uống thuốc, xác nhận qua ứng dụng kèm ảnh chụp.",
      },
      {
        step: "4",
        title: "Bác sĩ & người thân theo dõi",
        desc: "Cả hai đều thấy tình trạng tuân thủ, không cần hỏi qua điện thoại.",
      },
    ],
    // Nhac lai ngam ADR-0013: nguoi than KHONG tu ke/doi thuoc - chi buoc 1
    // (bac si) moi co quyen do. Ghi chu nay cho dev doc, khong hien len UI.
    note: "Người thân không tự kê hay đổi thuốc — chỉ bác sĩ mới có quyền đó.",
  },

  safety: {
    title: "Nguyên tắc an toàn",
    subtitle:
      "CapyMedi được thiết kế theo các nguyên tắc sau — không phải lời hứa marketing.",
    items: [
      {
        title: "Bác sĩ luôn là người quyết định",
        desc: "Mọi thay đổi phác đồ đều qua bác sĩ duyệt, không tự động hoá.",
      },
      {
        title: "Danh mục thuốc đóng, có kiểm soát",
        desc: "Chỉ kê được thuốc đã thẩm định; thuốc mới phải qua duyệt trước khi dùng.",
      },
      {
        title: "Chatbot được thiết kế để không kê đơn",
        desc: "Vai trò của chatbot là tra cứu thông tin, không đưa ra chỉ định điều trị.",
      },
      {
        title: "Phân quyền rõ theo vai trò",
        desc: "Bác sĩ, bệnh nhân, người thân, admin — mỗi người chỉ thấy đúng phần việc của mình.",
      },
    ],
  },

  trust: {
    title: "Vì sao chatbot không bịa thuốc",
    desc: "Mọi câu trả lời tra cứu đều lấy từ kho dữ liệu thuốc có nguồn gốc rõ ràng (hơn 3.500 loại), đang tiếp tục được thẩm định — không tự sinh thông tin y khoa.",
  },

  footer: {
    product: {
      title: "Sản phẩm",
      links: [
        { label: "Tính năng", href: "#capabilities" },
        { label: "Cách hoạt động", href: "#how-it-works" },
        { label: "An toàn", href: "#safety" },
      ],
    },
    account: {
      title: "Tài khoản",
      links: [
        { label: "Đăng nhập", href: "/login" },
        { label: "Đăng ký tài khoản", href: "/register" },
      ],
    },
    note: "CapyMedi là dự án MVP, đang trong giai đoạn phát triển và thử nghiệm.",
    copyright: (year: number) => `© ${year} CapyMedi. Bảo lưu mọi quyền.`,
  },
};
