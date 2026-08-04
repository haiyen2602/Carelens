#!/usr/bin/python
"""
Dem thuoc truc tiep bang camera: tu dong chup anh khi khung hinh dung yen,
chay model roi hien thong bao co bao nhieu vien thuoc.

    python camera_count.py [--camera 0] [--popup]

Phim tat trong cua so camera:
    SPACE : chup ngay khong cho tu dong
    R     : bo ket qua, quay lai che do cho tu dong chup
    Q/ESC : thoat
"""

import argparse
import ctypes
import os
import sys
import time

import cv2
import numpy as np

# predict.py load model bang duong dan tuong doi ('best.pt') nen phai dung dung thu muc
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from predict import get_prediction_details  # noqa: E402

WINDOW_NAME = 'Pill Counter'
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Kich thuoc anh xam dung de do do rung/chuyen dong, nho cho nhanh
DIFF_SIZE = (320, 240)


def to_gray(frame):
    '''
    Thu nho + lam mo khung hinh de so sanh chuyen dong cho on dinh
    '''
    small = cv2.resize(frame, DIFF_SIZE)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def frame_diff(gray_a, gray_b):
    '''
    Muc do khac nhau trung binh giua hai khung hinh (0 = y het)
    '''
    return float(np.mean(cv2.absdiff(gray_a, gray_b)))


def draw_banner(image, lines, color=(0, 0, 0)):
    '''
    Ve khung mo o tren cung roi viet cac dong chu len anh
    '''
    line_height = 34
    height = line_height * len(lines) + 16

    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (image.shape[1], height), color, -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)

    for i, line in enumerate(lines):
        y = 16 + line_height * i + 22
        cv2.putText(image, line, (14, y), FONT, 0.7, (255, 255, 255), 2, cv2.LINE_AA)


def format_confidence(per_class, class_name):
    '''
    Chuoi ' (95.2%)' cho loai thuoc co trong ket qua, chuoi rong neu khong co vien nao
    '''
    if class_name not in per_class:
        return ''
    return f' ({per_class[class_name] * 100:.1f}%)'


def show_popup(title, text):
    '''
    Hien hop thoai thong bao cua he dieu hanh, that bai thi bo qua
    '''
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)  # MB_ICONINFORMATION
        return
    except AttributeError:
        pass

    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showinfo(title, text)
        root.destroy()
    except Exception:
        pass


def count_pills(frame, output_dir):
    '''
    Chay model tren anh vua chup, luu anh ket qua,
    tra ve (anh da ve, so vien nang, so vien nen, do tu tin, duong dan anh)
    '''
    # get_prediction_details ve truc tiep len anh nen truyen ban sao de giu anh goc
    predicted_image, count_dict, confidence_dict = get_prediction_details(frame.copy())

    capsules = count_dict.get('capsules', 0)
    tablets = count_dict.get('tablets', 0)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, time.strftime('%Y%m%d_%H%M%S') + '.jpg')
    cv2.imwrite(output_path, predicted_image)

    return predicted_image, capsules, tablets, confidence_dict, output_path


#def open_camera(index, width, height):
    '''
    Mo camera, uu tien backend DirectShow tren Windows cho nhanh
    '''
    if sys.platform == 'win32':
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            capture = cv2.VideoCapture(index)
    else:
        capture = cv2.VideoCapture(index)

    if not capture.isOpened():
        return None

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def open_camera(index, width, height):
    # Ép OpenCV sử dụng backend DirectShow trên Windows
    if sys.platform == 'win32':
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    else:
        capture = cv2.VideoCapture(index)

    if not capture.isOpened():
        return None

    # QUAN TRỌNG: Ép định dạng khung hình sang MJPG để Camo truyền dữ liệu mượt mà, không bị đen màn hình
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    # Đặt độ phân giải
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    
    return capture

def parse_args():
    parser = argparse.ArgumentParser(description='Dem thuoc bang camera')
    parser.add_argument('--camera', type=int, default=0, help='Chi so camera (mac dinh 0)')
    parser.add_argument('--width', type=int, default=1280, help='Chieu rong khung hinh')
    parser.add_argument('--height', type=int, default=720, help='Chieu cao khung hinh')
    parser.add_argument('--still-threshold', type=float, default=2.0,
                        help='Duoi muc nay coi la khung hinh dung yen (mac dinh 2.0)')
    parser.add_argument('--motion-threshold', type=float, default=6.0,
                        help='Tren muc nay coi la co chuyen dong, san sang chup lai (mac dinh 6.0)')
    parser.add_argument('--still-frames', type=int, default=15,
                        help='So khung hinh phai dung yen lien tuc truoc khi chup (mac dinh 15)')
    parser.add_argument('--output-dir', default='captures', help='Thu muc luu anh ket qua')
    parser.add_argument('--popup', action='store_true',
                        help='Hien them hop thoai thong bao sau moi lan dem')
    return parser.parse_args()


def main():
    args = parse_args()

    capture = open_camera(args.camera, args.width, args.height)
    if capture is None:
        print(f'Khong mo duoc camera {args.camera}. Thu --camera 1 hoac kiem tra quyen camera.')
        sys.exit(1)

    print('Camera dang chay. Dat thuoc vao khung hinh va giu yen, chuong trinh se tu chup.')
    print('SPACE = chup ngay | R = chup lai | Q/ESC = thoat')

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    previous_gray = None
    still_count = 0
    # Cho camera on dinh anh sang truoc khi cho phep chup
    warmup_frames = 10

    result_image = None   # Khac None nghia la dang hien ket qua
    result_lines = []

    while True:
        ok, frame = capture.read()
        if not ok:
            print('Mat ket noi camera.')
            break

        frame = cv2.flip(frame, 1)  # Lat guong cho de canh tay
        gray = to_gray(frame)

        difference = 0.0 if previous_gray is None else frame_diff(previous_gray, gray)
        previous_gray = gray

        if warmup_frames > 0:
            warmup_frames -= 1

        capture_now = False

        if result_image is None:
            # Dang xem truc tiep, dem so khung hinh dung yen
            if warmup_frames == 0 and difference < args.still_threshold:
                still_count += 1
            else:
                still_count = 0

            if still_count >= args.still_frames:
                capture_now = True

            progress = min(still_count, args.still_frames)
            display = frame.copy()
            draw_banner(display, [
                'Dat thuoc vao khung hinh va giu yen...',
                'On dinh: ' + '#' * progress + '-' * (args.still_frames - progress),
            ])
        else:
            # Dang hien ket qua, co chuyen dong manh thi quay lai xem truc tiep
            if difference > args.motion_threshold:
                result_image = None
                still_count = 0
                warmup_frames = 10
                continue
            display = result_image

        cv2.imshow(WINDOW_NAME, display)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        if key == ord('r'):
            result_image = None
            still_count = 0
            warmup_frames = 10
            continue
        if key == 32:  # SPACE
            capture_now = True

        if not capture_now:
            continue

        # Chup va dem
        still_count = 0
        busy_image = frame.copy()
        draw_banner(busy_image, ['Dang dem...'])
        cv2.imshow(WINDOW_NAME, busy_image)
        cv2.waitKey(1)

        predicted_image, capsules, tablets, confidence_dict, output_path = count_pills(
            frame, args.output_dir)
        total = capsules + tablets

        if total == 0:
            result_lines = ['Khong tim thay vien thuoc nao', 'Nhan R hoac di chuyen de chup lai']
        else:
            per_class = confidence_dict.get('per_class', {})
            result_lines = [
                f"Tong cong: {total} vien - do tin cay {confidence_dict['mean'] * 100:.1f}%",
                (f'Vien nang (capsules): {capsules}{format_confidence(per_class, "capsules")}'
                 f' | Vien nen (tablets): {tablets}{format_confidence(per_class, "tablets")}'),
                f"Vien co do tu tin thap nhat: {confidence_dict['min'] * 100:.1f}%",
                'Nhan R hoac di chuyen de chup lai',
            ]

        print(f'Vien nang (capsules): {capsules}')
        print(f'Vien nen  (tablets) : {tablets}')
        print(f'Tong cong           : {total}')
        if confidence_dict:
            print(f"Do tin cay trung binh: {confidence_dict['mean'] * 100:.1f}%")
            print(f"Do tin cay thap nhat : {confidence_dict['min'] * 100:.1f}%")
            for name, value in confidence_dict['per_class'].items():
                print(f'  - {name}: {value * 100:.1f}%')
        print(f'Da luu anh ket qua  : {output_path}\n')

        result_image = predicted_image
        draw_banner(result_image, result_lines)
        cv2.imshow(WINDOW_NAME, result_image)
        cv2.waitKey(1)

        if args.popup:
            show_popup('Ket qua dem thuoc', '\n'.join(result_lines[:-1]))

        # Bo qua khung hinh cu de khong bat nham chuyen dong luc dang chay model
        previous_gray = None

    capture.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
