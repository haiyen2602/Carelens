import assert from "node:assert/strict";

import { UU_TIEN_MIME, tenFileGhiAm } from "../src/lib/voice-format.ts";

// Bug that tren iPhone (2026-08-28): ten file tung hard-code "voice.webm"
// trong khi Safari iOS khong ho tro webm va ghi ra MP4. OpenAI doc dinh dang
// theo DUOI ten file - do thuc te bang mot file mp3 duy nhat: gui ten
// "voice.mp3" nhan dung, gui ten "voice.webm" tra ve "Audio file might be
// corrupted or unsupported". Nen moi luot ghi am tren iPhone hong 100%.
assert.equal(tenFileGhiAm("audio/mp4"), "voice.mp4");
assert.equal(tenFileGhiAm("audio/webm"), "voice.webm");
assert.equal(tenFileGhiAm("audio/ogg"), "voice.ogg");

// MediaRecorder tra ve mime KEM codec - phan sau dau ; khong duoc lam hong
// phep tra duoi. Chrome desktop that su tra ve chuoi dang nay.
assert.equal(tenFileGhiAm("audio/webm;codecs=opus"), "voice.webm");
assert.equal(tenFileGhiAm("audio/mp4; codecs=mp4a.40.2"), "voice.mp4");
assert.equal(tenFileGhiAm("AUDIO/WEBM"), "voice.webm");

// Mime la nao khong biet -> KHONG duoi, de OpenAI tu do noi dung. Doan bua
// mot duoi sai thi hong chac chan, con khong duoi thi da do la van nhan dung.
assert.equal(tenFileGhiAm("audio/x-la-lam"), "voice");
assert.equal(tenFileGhiAm(""), "voice");
assert.equal(tenFileGhiAm(undefined), "voice");
assert.equal(tenFileGhiAm(null), "voice");

// webm phai duoc uu tien dau tien (chat luong/dung luong tot hon tren
// Chrome), nhung mp4 PHAI co trong danh sach - do la duong duy nhat cua iOS.
assert.equal(UU_TIEN_MIME[0], "audio/webm");
assert.ok(UU_TIEN_MIME.includes("audio/mp4"), "thieu audio/mp4 -> iPhone lai hong");

console.log("voice-format: tat ca assertion deu dat");
