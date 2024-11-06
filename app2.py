from fastapi import FastAPI,  status
from fastapi.responses import JSONResponse
import serial
import asyncio, json, time


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
        with serial.Serial("/dev/ttyAMA0", 115200, timeout=1) as ser:
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