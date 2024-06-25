from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
import serial
import json
import cv2
import time
from camera import IdsCamera
import os
from starlette.responses import StreamingResponse
folder_path = './output'
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

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
            return JSONResponse(content=responses, status_code=status.HTTP_200_OK)
        else:
            return JSONResponse(content="No response from UART device", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except serial.SerialException as e:
        return JSONResponse(content=f"Serial communication error: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return JSONResponse(content=f"An error occurred: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


app = FastAPI()
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

@app.get('/video_feed')
async def video_feed():
    return StreamingResponse(generate_frames(), media_type='multipart/x-mixed-replace; boundary=frame')

@app.get("/status")
async def get_status():
    return communicate_with_serial({"cmd": "status"})

@app.get("/location")
async def get_camera_location():
    return communicate_with_serial({"cmd": "get_x"})

@app.get("/stop")
async def stop_moving_camera():
    return communicate_with_serial({"cmd": "halt"})

@app.get("/go/{x}")
async def go_moving_camera(x: str):
    return communicate_with_serial({"cmd": "go_x", "x": x}, 2)

@app.get("/calibrate")
async def calibrate():
    return communicate_with_serial({"cmd": "calibrate"})

@app.get("/setmaximum/manual/{x_max}")
async def set_maximum_manual(x_max: str):
    return communicate_with_serial({"cmd": "calibrate", "set_type": "manual", "x_max": x_max})

@app.get("/setmaximum/auto")
async def set_maximum_auto():
    return communicate_with_serial({"cmd": "calibrate", "set_type": "limit_sw"})


@app.get("/get_image")
async def get_image():
    image_path = makeFileName()
    camera = IdsCamera()
    camera.set_image_handler(lambda image: cv2.imwrite(image_path, image))



if __name__ == "__main__":
    
