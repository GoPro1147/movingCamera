from fastapi import FastAPI,  status,  BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import cv2, serial, numpy as np
import asyncio, json, time, os, sys
# from camera2 import takePicture
from camera3 import IdsCamera
from threading import Thread, Lock


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

async def communicate_with_serial(command, response_count=1):
    try:
        def serial_operation():
            ser = serial.Serial("/dev/ttyAMA0", 115200, timeout=1)
            send_json_data(ser, command)
            return receive_multiple_responses(ser, response_count)
            
        # serial 통신을 비동기 이벤트 루프에서 실행
        result = await asyncio.to_thread(serial_operation)
        return result
        
    except serial.SerialException as e:
        return JSONResponse(content=f"Serial communication error: {e}", 
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return JSONResponse(content=f"An error occurred: {e}", 
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

def makeFileName():
    timestr = time.strftime("%Y%m%d-%H_%M_%S")
    return f"./output/{timestr}.jpeg"


app = FastAPI()
            

@app.get("/status")
async def get_status():
    return await communicate_with_serial({"cmd": "status"})

@app.get("/location")
async def get_camera_location():
    return await communicate_with_serial({"cmd": "get_x"})

@app.get("/stop")
async def stop_moving_camera():
    return await communicate_with_serial({"cmd": "halt"})

@app.get("/go/{x}")
async def go_moving_camera(x: str):
    return await communicate_with_serial({"cmd": "go_x", "x": x}, 2)

@app.get("/calibrate")
async def calibrate():
    return await communicate_with_serial({"cmd": "calibrate"})

@app.get("/setmaximum/manual/{x_max}")
async def set_maximum_manual(x_max: str):
    return await communicate_with_serial({"cmd": "calibrate", "set_type": "manual", "x_max": x_max})

@app.get("/setmaximum/auto")
async def set_maximum_auto():
    return await communicate_with_serial({"cmd": "calibrate", "set_type": "limit_sw"})


@app.get("/get_image")
async def get_image(background_tasks: BackgroundTasks):
    global output_frame, lock

    with lock:
        if output_frame is None:
            return JSONResponse(content="No frame available", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        frame = output_frame

    # 파일로 저장
    image_path = makeFileName()
    with open(image_path, 'wb') as f:
        f.write(frame)

    # 파일 응답 생성
    response = FileResponse(image_path)

    # 파일 삭제를 백그라운드 태스크로 등록
    background_tasks.add_task(delete_file, image_path)

    return response

# 전역 변수로 카메라 객체 선언
camera = None

def initialize_camera():
    global camera
    try:
        camera = IdsCamera()
        return True
    except Exception as e:
        print(f"카메라 초기화 실패: {str(e)}")
        return False

# 프로그램 시작시 카메라 초기화
if not initialize_camera():
    print("프로그램을 종료합니다.")
    sys.exit(1)

def capture_frames():
    global output_frame, lock, camera
    
    while True:
        try:
            img = next(camera.streaming_image())
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            # img_bgr = cv2.resize(img_bgr, (640, 480))

            _, buffer = cv2.imencode('.jpg', img_bgr)
            data = buffer.tobytes()

            with lock:
                output_frame = data

            # 메모리 해제
            del img
            del img_bgr
            del buffer
            
        except StopIteration:
            print("카메라 스트림 종료 - 재연결 시도")
            camera = None  # 카메라 객체 초기화
            time.sleep(1)  # 재연결 전 잠시 대기
            continue
        except Exception as e:
            print(f"프레임 생성 중 오류 발생: {str(e)}")
            camera = None  # 에러 발생 시 카메라 객체 초기화
            time.sleep(1)
            continue

lock = Lock()
output_frame = None

thread = Thread(target=capture_frames)
thread.daemon = True
thread.start()

def generate_frames():
    global output_frame, lock
    
    while True:
        try:
            with lock:
                if output_frame is None:
                    time.sleep(0.1)  # CPU 사용량 감소
                    continue
                frame = output_frame.copy()  # 데이터 복사
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                   
        except Exception as e:
            print(f"프레임 전송 중 오류 발생: {str(e)}")
            time.sleep(0.1)
            continue

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type='multipart/x-mixed-replace; boundary=frame')
