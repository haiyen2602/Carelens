// Bo anh + quote cua Capy - chep tu public/capy_quotes.md, moi muc ung voi
// dung 1 file anh trong public/. Sua noi dung o ca 2 noi neu doi.

export type CapyQuote = {
  /** Ten file trong public/ */
  src: string;
  /** Mo ta anh - dung lam alt cho trinh doc man hinh */
  alt: string;
  /** Dong to */
  line: string;
  /** Dong be */
  sub: string;
};

export const CAPY_QUOTES: CapyQuote[] = [
  {
    src: "/capy_chao.png",
    alt: "Capy đội mũ y tá, giơ tay chào",
    line: "Capy chào bạn nè!",
    sub: "Một ngày dễ thương bắt đầu từ lời chào.",
  },
  {
    src: "/capy_ngai.png",
    alt: "Capy đội mũ y tá, hai tay gần má, biểu cảm ngại ngùng",
    line: "Capy hơi ngại một chút.",
    sub: "Nhưng vẫn muốn ở cạnh bạn đó.",
  },
  {
    src: "/capy_khoc.png",
    alt: "Capy đội mũ y tá, mắt rưng rưng",
    line: "Capy cần được dỗ.",
    sub: "Hôm nay cho Capy buồn một tí nha.",
  },
  {
    src: "/capy_yeu.png",
    alt: "Capy đội mũ y tá, ôm một trái tim lớn",
    line: "Capy gửi bạn một trái tim.",
    sub: "Thêm chút yêu thương cho ngày hôm nay.",
  },
  {
    src: "/capy_camon.png",
    alt: "Capy đội mũ y tá, chắp hai tay trước ngực",
    line: "Capy cảm ơn bạn nhiều lắm.",
    sub: "Có bạn là mọi chuyện nhẹ nhàng hơn rồi.",
  },
  {
    src: "/capy_ngu.png",
    alt: "Capy đội mũ y tá, nằm ngủ trên gối xanh",
    line: "Capy ngủ một lát nha.",
    sub: "Nghỉ ngơi cũng là một việc quan trọng.",
  },
  {
    src: "/capy_vui.png",
    alt: "Capy đội mũ y tá, giơ hai tay lên cao hào hứng",
    line: "Capy đang rất vui!",
    sub: "Chia bạn một chút năng lượng tích cực nè.",
  },
  {
    src: "/capy_ngau.png",
    alt: "Capy đội mũ y tá, đeo kính đen, khoanh tay",
    line: "Capy hôm nay hơi ngầu.",
    sub: "Bình tĩnh, chuyện gì rồi cũng xử lý được.",
  },
];

/**
 * Chon ngau nhien 1 muc. PHAI goi trong useEffect (khong phai luc render):
 * trang nay duoc server-render truoc, neu random ngay luc render thi HTML
 * cua server va cua trinh duyet khac nhau -> React bao loi hydration.
 */
export function randomCapyQuote(): CapyQuote {
  return CAPY_QUOTES[Math.floor(Math.random() * CAPY_QUOTES.length)];
}
