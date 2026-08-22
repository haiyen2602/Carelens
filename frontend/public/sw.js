// Service Worker cua CapyMedi - THEM 2026-08-20.
//
// Muc dich DUY NHAT: nhan Web Push va hien thong bao he thong ke ca khi
// nguoi dung DA DONG HAN tab/trinh duyet. Day la thu ma code binh thuong
// trong trang khong lam duoc - code do chet theo tab, con Service Worker
// duoc trinh duyet danh thuc day rieng khi co tin day toi.
//
// CO Y KHONG lam caching/offline o day. Them cache vao Service Worker cho
// 1 app Next.js co du lieu y te thay doi lien tuc la ruoc them 1 lop du
// lieu cu kho go - neu sau nay can offline thi phai thiet ke rieng.

self.addEventListener("install", () => {
  // Kich hoat ban SW moi ngay, khong doi tab cu dong het - nguoi dung khong
  // nen phai dong het tab moi nhan duoc ban sua loi cua SW.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  // LUON hien thong bao, khong im lang ke ca khi tab dang mo: spec
  // userVisibleOnly bat buoc moi lan nhan push phai hien 1 thong bao, neu
  // khong Chrome tu hien "site da cap nhat ngam" va phat neu lap lai.
  // Chong bao trung duoc xu ly o phia trang (capy-shell.tsx thoi tu ban
  // Notification he thong khi da dang ky push), khong phai o day.
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    // Payload hong/khong phai JSON - van hien 1 thong bao chung chung con
    // hon la nuot mat lan nhac uong thuoc.
  }

  const title = data.title || "CapyMedi";
  const options = {
    body: data.body || "Đã đến giờ uống thuốc",
    icon: "/capy_nhacnho.png",
    badge: "/favicon-64.png",
    // Chi chay tren Android - iOS chua bao gio ho tro Vibration API. Khong
    // loi, chi im lang bo qua.
    vibrate: [200, 100, 200],
    // Cung tag => thong bao moi THAY THE cai cu thay vi chat dong: nhac lai
    // cung 1 lieu khong nen de lai 3 dong trong khay thong bao.
    tag: "capymedi-dose-reminder",
    renotify: true,
    data: { url: data.url || "/patient" },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/patient";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      // Uu tien focus tab CapyMedi dang mo san thay vi mo them tab moi -
      // mo trung 2 tab cung app la trai nghiem tệ tren dien thoai.
      for (const client of clientList) {
        if (client.url.includes("/patient") && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});
