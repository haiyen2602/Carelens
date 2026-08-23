# Kết quả eval VLM (đếm thuốc)

Chạy lúc: 2026-08-22T18:42:01.312261+00:00
Model: `openai/cd/gpt-5.5`

**Tổng: 12/25 đạt (48.0%)**

| Độ khó | Đạt/Tổng | % |
|---|---|---|
| Dễ | 7/8 | 87.5% |
| Trung bình | 3/12 | 25.0% |
| Khó | 2/5 | 40.0% |

| Độ tin cậy | Đạt/Tổng | % |
|---|---|---|
| trung_binh | 3/5 | 60.0% |
| thap | 0/11 | 0.0% |
| cao | 9/9 | 100.0% |

## Chi tiết từng case

| Case | Độ khó | Kỳ vọng | Thực tế (khác 0) | Độ tin cậy | Kết quả |
|---|---|---|---|---|---|
| anh_1 | Dễ | Viên nén=2 | vien_nen=2 | trung_binh | ✅ |
| anh_2 | Trung bình | Viên nén=2 | (rỗng) | thap | ❌ |
| anh_3 | Dễ | Viên nang=2 | vien_nang=2 | cao | ✅ |
| anh_4 | Trung bình | Viên nang=2 | vien_nen=2 | thap | ❌ |
| anh_5 | Dễ | Lọ thuốc=1 | lo_thuoc=1 | cao | ✅ |
| anh_6 | Dễ | Tuýp thuốc=1 | tuyp_thuoc=1 | cao | ✅ |
| anh_7 | Dễ | Viên nang=2, viên nén=2 | vien_nang=2 | thap | ❌ |
| anh_8 | Trung bình | Viên nén=2, viên nang=2 | vien_nen=2 | thap | ❌ |
| anh_9 | Trung bình | Viên nang=4, viên nén=2 | vien_nang=2, vien_nen=3 | trung_binh | ❌ |
| anh_10 | Khó | Viên nang=4, viên nén=2 | (rỗng) | thap | ❌ |
| anh_11 | Dễ | Lọ thuốc=1, viên nang=2 | vien_nang=2, lo_thuoc=1 | cao | ✅ |
| anh_12 | Khó | Không phải thuốc | (rỗng) | cao | ✅ |
| anh_13 | Khó | Viên nang=4, viên nén=4 | vien_nen=4 | thap | ❌ |
| anh_14 | Trung bình | Lọ thuốc = 1 | lo_thuoc=1 | cao | ✅ |
| anh_15 | Khó | Lọ thuốc = 1 | lo_thuoc=1 | cao | ✅ |
| anh_16 | Trung bình | Viên nang=4, viên nén=4 | (rỗng) | thap | ❌ |
| anh_17 | Trung bình | Tuýp thuốc=1 | tuyp_thuoc=1 | trung_binh | ✅ |
| anh_18 | Trung bình | Lọ thuốc=1 | goi_thuoc=1 | thap | ❌ |
| anh_19 | Dễ | Gói thuốc=1 | goi_thuoc=1 | cao | ✅ |
| anh_20 | Trung bình | Gói thuốc=1 | lo_thuoc=1 | thap | ❌ |
| anh_21 | Dễ | Ống thuốc = 1 | lo_thuoc=1 | cao | ✅ |
| anh_22 | Trung bình | Ống thuốc = 1 | (rỗng) | thap | ❌ |
| anh_23 | Trung bình | Lọ thuốc=1, tuýp thuốc=2, viên nang=2, viên nén=2 | vien_nang=1, vien_nen=2, tuyp_thuoc=2, lo_thuoc=1 | thap | ❌ |
| anh_24 | Khó | Lọ thuốc=1, tuýp thuốc=2, viên nang=2, viên nén=2 | vien_nang=4, tuyp_thuoc=2, lo_thuoc=1 | trung_binh | ❌ |
| anh_25 | Trung bình | Viên nén=1 | vien_nen=1 | trung_binh | ✅ |