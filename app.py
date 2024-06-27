from fastapi import FastAPI,  status,  BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import cv2, serial
import asyncio, json, time, os
from camera import IdsCamera


folder_path = './output'
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

def delete_file(file_path: str):
    if os.path.exists(file_path):  # 파일이 존재하는지 확인
        os.remove(file_path)  # 파일 삭제

def send_json_data(ser, data):
    try:
        # 데이터 전송
        ser.write(json.dumps(data).encode('utf-8') + b'\n')
    except Exception as e:
        print(f"Error communicating with serial device: {e}")
    finally:
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
            
def makeFileName():
    timestr = time.strftime("%Y%m%d-%H_%M_%S")
    return f"./output/{timestr}.jpeg"

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
async def get_image(background_tasks: BackgroundTasks):
    image_path = makeFileName()
    camera = IdsCamera()

    image_captured_event = asyncio.Event()

    def image_handler(image):
        cv2.imwrite(image_path, image)
        image_captured_event.set()

    camera.set_image_handler(image_handler)
    camera.single_shot()

    # 카메라가 이미지 캡처를 완료할 때까지 대기
    await image_captured_event.wait()

    # 이미지 캡처가 완료된 후 응답 생성
    response = FileResponse(image_path)

    # 파일 삭제를 백그라운드 태스크로 등록
    background_tasks.add_task(delete_file, image_path)

    return response