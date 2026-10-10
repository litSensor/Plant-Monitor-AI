import cv2, glob
paths = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
if not paths:
    print("USB-камер не найдено"); raise SystemExit(1)
for p in paths:
    cap = cv2.VideoCapture(p, cv2.CAP_V4L2)
    if not cap.isOpened(): print(f"[FAIL] {p}"); continue
    ok, f = cap.read()
    print(f"[OK]   {p}  {f.shape if ok else 'нет кадра'}")
    cap.release()
