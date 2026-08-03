#!/usr/bin/python
"""
Chay model dem thuoc doc lap, khong can Telegram.

    python predict.py <duong_dan_anh> [anh_ket_qua]
"""

import sys

import cv2
import numpy as np
from shapely.geometry import Polygon
from ultralytics import YOLO

COLORS = [(98, 231, 4), (228, 161, 0)]  # Green and blue
CLASSES = ['capsules', 'tablets']

# Load model mot lan duy nhat luc khoi dong, khong load lai moi anh
model = YOLO('best.pt')


def get_prediction(image):
    '''
    Gets image, makes predictions, counts predicted classes,
    draws dots on image, returns dict with counts and labelled image
    '''
    prediction = model(image, verbose=False)

    masks = prediction[0].masks
    # Anh khong co vien thuoc nao -> masks la None
    if masks is None:
        return image, {}

    predicted_classes = prediction[0].boxes.cls
    prediction_confidences = prediction[0].boxes.conf

    polygons = [polygon.astype(np.int32) for polygon in masks.xy]

    indices_mask = remove_overlapping_polygons(polygons, prediction_confidences)

    fixed_predicted_classes = predicted_classes[np.array(indices_mask, dtype=bool)]
    fixed_polygons = [polygons[i] for i in range(len(indices_mask)) if indices_mask[i] == 1]

    unique, counts = fixed_predicted_classes.unique(return_counts=True)
    count_dict = {CLASSES[int(key)]: value for key, value in zip(unique.tolist(), counts.tolist())}

    # Draw dots
    for polygon, predicted_class in zip(fixed_polygons, fixed_predicted_classes):
        center_coordinates = (np.mean(polygon[:, 0], dtype=np.int32),
                              np.mean(polygon[:, 1], dtype=np.int32))  # x and y respectively
        cv2.circle(image, center_coordinates, 5, COLORS[int(predicted_class)], 2, cv2.LINE_AA)

    return image, count_dict


def remove_overlapping_polygons(polygons, prediction_confidences):
    '''
    Takes polygons, finds overlapping regions, intersection area,
    overlap percentage, creates indices mask that shows what
    overlapping polygon has smaller confidence.
    '''
    shapely_polygons = []
    for polygon in polygons:
        # Shapely can it nhat 3 diem moi tao duoc vung
        if len(polygon) < 3:
            shapely_polygons.append(None)
            continue
        shapely_polygons.append(Polygon(polygon).buffer(0))

    indices_mask = [1 for _ in range(len(shapely_polygons))]

    for i in range(len(shapely_polygons)):
        if shapely_polygons[i] is None:
            indices_mask[i] = 0
            continue
        for j in range(i + 1, len(shapely_polygons)):
            if shapely_polygons[j] is None:
                continue
            # Bo qua polygon da bi loai o vong truoc
            if indices_mask[i] == 0 or indices_mask[j] == 0:
                continue
            if not shapely_polygons[i].intersects(shapely_polygons[j]):
                continue

            intersection_area = shapely_polygons[i].intersection(shapely_polygons[j]).area
            smaller_area = min(shapely_polygons[i].area, shapely_polygons[j].area)
            if smaller_area == 0:
                continue

            if intersection_area / smaller_area > 0.5:
                # Loai cai co confidence thap hon
                if prediction_confidences[i] >= prediction_confidences[j]:
                    indices_mask[j] = 0
                else:
                    indices_mask[i] = 0

    return indices_mask


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    image_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'ket_qua.jpg'

    image = cv2.imread(image_path)
    if image is None:
        print(f'Khong doc duoc anh: {image_path}')
        sys.exit(1)

    predicted_image, count_dict = get_prediction(image)

    capsules = count_dict.get('capsules', 0)
    tablets = count_dict.get('tablets', 0)
    print(f'Vien nang (capsules): {capsules}')
    print(f'Vien nen  (tablets) : {tablets}')
    print(f'Tong cong           : {capsules + tablets}')

    cv2.imwrite(output_path, predicted_image)
    print(f'Da luu anh ket qua  : {output_path}')


if __name__ == '__main__':
    main()
