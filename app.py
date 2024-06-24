from flask import Flask, Response, jsonify, make_response
import serial
import json
import cv2
import time
from camera import IdsCamera
import os





def on_image(image):
    print(f"Image Shape : {image.shape}")
    cv2.imwrite('test.png', image)


def send_json_data(ser, data):
    try:
        # 데이터 전송
        ser.write(json.dumps(data).encode('utf-8') + b'\n')
        # 응답 수신
        response = ser.readline().decode('utf-8')
        return json.loads(response)
    except Exception as e:
        print(f"Error communicating with serial device: {e}")
        return None


def receive_multiple_responses(ser, response_count=1):
    responses = []
    try:
        while len(responses) < response_count:
            line = ser.readline().decode('utf-8').strip()
            if line:
                responses.append(json.loads(line))
    except Exception as e:
        print(f"Error receiving data from serial device: {e}")
        return None
    return responses

def communicate_with_serial(command, response_count=1):
    try:
        with serial.Serial("/dev/ttyUSB0", 115200, timeout=1) as ser:
            send_json_data(ser, command)
            responses = receive_multiple_responses(ser, response_count)
        if responses:
            return make_response(jsonify(responses), 200)
        else:
            return make_response("No response from UART device", 500)
    except serial.SerialException as e:
        return make_response(f"Serial communication error: {e}", 500)
    except Exception as e:
        return make_response(f"An error occurred: {e}", 500)


app = Flask(__name__)
# RTSP 스트림 URL
rtsp_url = "rtsp://username:password@camera_ip:port/path"

def generate_frames():
    cap = cv2.VideoCapture(rtsp_url)
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
def makeFileName():
    timestr = time.strftime("%Y%m%d-%H_%M_%S")
    return f"./output/{timestr}.png"

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/status", methods=["GET"])
def get_status():
    return communicate_with_serial({"cmd": "status"})

@app.route("/location", methods=["GET"])
def get_camera_location():
    return communicate_with_serial({"cmd": "get_x"})

@app.route("/stop", methods=["GET"])
def stop_moving_camera():
    return communicate_with_serial({"cmd": "halt"})

@app.route("/go/<x>", methods=["GET"])
def go_moving_camera(x):
    return communicate_with_serial({"cmd": "go_x", "x": x}, 2)

@app.route("/calibrate", methods=["GET"])
def calibrate():
    return communicate_with_serial({"cmd": "calibrate"})

@app.route("/setmaximum/manual/<x_max>", methods=["GET"])
def set_maximum_manual(x_max):
    return communicate_with_serial({"cmd": "calibrate", "set_type": "manual", "x_max": x_max})

@app.route("/setmaximum/auto", methods=["GET"])
def set_maximum_manual():
    return communicate_with_serial({"cmd": "calibrate", "set_type": "limit_sw"})


@app.route("/get_image", methods=["GET"])
def get_image():
    image_path = makeFileName()
    camera = IdsCamera()
    camera.set_image_handler(lambda image: cv2.imwrite('test.png', image))



if __name__ == "__main__":
    folder_path = './output'
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    app.run(host="0.0.0.0", port=5000, debug=True)