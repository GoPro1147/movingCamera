import os
os.environ['GENICAM_GENTL64_PATH'] = '/usr/lib/ids/cti'
from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak import ids_peak_ipl_extension

from typing import Callable

import cv2 
import numpy as np
from loguru import logger
from datetime import datetime
import copy
import threading

class IdsCamera(object):
    def __init__(self):
        self.node_map_remote_device = None
        self.imageAquisitionThread = threading.Thread(target=self.image_aquisition, args=())
        self.imageAquisitionThread.start()
        self.__busy = False
        self.__camera_ready = False
        self.__keep_running = True
        self.__onImageHandler = None

    def set_image_handler(self, proc: Callable[[np.ndarray], None]): 
        self.__onImageHandler = proc
    
    def open_camera(self):
        try:
            # Create instance of the device manager
            device_manager = ids_peak.DeviceManager.Instance()
            # Update the device manager
            device_manager.Update()
            # Return if no device was found
            if device_manager.Devices().empty():
                return False
            # open the first openable device in the device manager's device list
            device_count = device_manager.Devices().size()
            for i in range(device_count):
                if device_manager.Devices()[i].IsOpenable():
                    m_device = device_manager.Devices()[i].OpenDevice(ids_peak.DeviceAccessType_Control)
                    # Get NodeMap of the RemoteDevice for all accesses to the GenICam NodeMap tree
                    #m_node_map_remote_device = m_device.RemoteDevice().NodeMaps()[0] 
                    return m_device
        except Exception as e:
            print(e)
        logger.error("No Device Found")
        return None

    def busy(self):
        return self.__busy

    def single_shot(self): 
        if not self.__camera_ready: 
            logger.info("waiting for camera ready")
            return
        elif self.node_map_remote_device is None:
            logger.error("Camera is not initalizaed")
            return
        elif self.__busy:
            logger.error("Camera is busy")
            return
        self.__busy = True
        self.node_map_remote_device.FindNode("TriggerSoftware").Execute()

    def image_aquisition(self):
        ids_peak.Library.Initialize()
        try:
            self.device = self.open_camera() 
        except Exception as e:
            logger.error('Failed to open camera')
        try:

            self.node_map_remote_device = self.device.RemoteDevice().NodeMaps()[0]
            self.node_map_remote_device.FindNode("UserSetSelector").SetCurrentEntry("Default")
            self.node_map_remote_device.FindNode("UserSetLoad").Execute()
            #self.node_map_remote_device.FindNode("TriggerSelector").SetCurrentEntry("ReadOutStart")
            self.node_map_remote_device.FindNode("TriggerMode").SetCurrentEntry("On")
            self.node_map_remote_device.FindNode("TriggerSource").SetCurrentEntry("Software")
            self.node_map_remote_device.FindNode("GainAuto").SetCurrentEntry("Continuous")
            
            #self.node_map_remote_device.FindNode("ExposureAuto").SetCurrentEntry("Continuous")
            self.node_map_remote_device.FindNode("ExposureAuto").SetCurrentEntry("Off")
            self.node_map_remote_device.FindNode("ExposureTime").SetValue(18000)

            self.datastreams = self.device.DataStreams()
            if self.datastreams.empty():
                logger.error("No datastreams found")
                return
            self.datastream = self.datastreams[0].OpenDataStream()
            if self.datastream:
            # Flush queue and prepare all buffers for revoking
                self.datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            # Clear all old buffers
                for buffer in self.datastream.AnnouncedBuffers():
                    self.datastream.RevokeBuffer(buffer)
                payload_size = self.node_map_remote_device.FindNode("PayloadSize").Value()
                # Get number of minimum required buffers
                num_buffers_min_required = self.datastream.NumBuffersAnnouncedMinRequired()
                # Alloc buffers
                for count in range(num_buffers_min_required):
                    buffer = self.datastream.AllocAndAnnounceBuffer(payload_size)
                    self.datastream.QueueBuffer(buffer)

            self.datastream.StartAcquisition(ids_peak.AcquisitionStartMode_Default, ids_peak.DataStream.INFINITE_NUMBER)
            self.node_map_remote_device.FindNode("TLParamsLocked").SetValue(1)
            self.node_map_remote_device.FindNode("AcquisitionStart").Execute()
            self.__camera_ready = True
            while self.__keep_running:
                try:
                    _buffer = self.datastream.WaitForFinishedBuffer(500)
                except ids_peak.TimeoutException as e:
                    continue
                ipl_image = ids_peak_ipl_extension.BufferToImage(_buffer)
                self.datastream.QueueBuffer(_buffer)
                converted_ipl_image = ipl_image.ConvertTo(ids_peak_ipl.PixelFormatName_BGRa8)
                image_np_array = converted_ipl_image.get_numpy()
                self.__onImageHandler(copy.copy(image_np_array))
                self.__busy = False
        except Exception as e: 
            logger.error(f"Error in U3 image acquisition: {e}")
            print(e)

        ids_peak.Library.Close()

    def stop(self): 
        self.__keep_running = False
        self.imageAquisitionThread.join()

#------------------------------- example below

def on_image(image):
    print(f"Image Shape : {image.shape}")
    cv2.imwrite('test.jpg', image)


if __name__ == "__main__":
    import time

    camera = IdsCamera()
    camera.set_image_handler(lambda image: cv2.imwrite('test.png', image))

    while True:
        try:
            camera.single_shot()

            time.sleep(2)

            # for sync 
            while camera.busy():
                pass

            
        except KeyboardInterrupt: 
            print("Exiting...")
            camera.stop()
            break
    