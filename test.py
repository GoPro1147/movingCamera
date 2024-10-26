from camera3 import IdsCamera
import cv2

def display_stream():
    camera = IdsCamera()
    while True:
        img = next(camera.streaming_image())
        # Convert RGBa8 to BGR for OpenCV
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        img_bgr = cv2.resize(img_bgr, (640, 480))

        # Display the image using OpenCV
        cv2.imshow('Camera Stream', img_bgr)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    display_stream()
