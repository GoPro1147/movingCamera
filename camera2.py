import sys, os
os.environ['GENICAM_GENTL64_PATH'] = '/usr/lib/ids/cti'
from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak import ids_peak_ipl_extension
import threading
import time
from loguru import logger
 
import cv2 

def open_camera():
    global m_node_map_remote_device
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
    return None

def setCameraParams(device, autoExposure=True): 
    try:
        node_map_remote_device = device.RemoteDevice().NodeMaps()[0]
        # Get the NodeMap of the RemoteDevice
        if autoExposure:
            node_map_remote_device.FindNode("ExposureAuto").SetCurrentEntry("Continuous")
        else:              
            node_map_remote_device.FindNode("ExposureAuto").SetCurrentEntry("Off")
            node_map_remote_device.FindNode("ExposureTime").SetValue(14996.9 )
        
    except Exception as e:
        print(e)
        
def trigger(node_map_remote_device):
    time.sleep(2)
    node_map_remote_device.FindNode("TriggerSoftware").Execute()

def imageAquisition(datastream, filename):
    _buffer = datastream.WaitForFinishedBuffer(10000)
    ipl_image = ids_peak_ipl_extension.BufferToImage(_buffer)
    converted_ipl_image = ipl_image.ConvertTo(ids_peak_ipl.PixelFormatName_BGRa8)
    image_np_array = converted_ipl_image.get_numpy()
    cv2.imwrite(filename, image_np_array)
    datastream.QueueBuffer(_buffer)
    ids_peak.Library.Close()
    logger.success("image aquisition done")

def makeFileName():
    timestr = time.strftime("%Y%m%d-%H_%M_%S")
    return f"./output/{timestr}.png"

def takePicture():
    ids_peak.Library.Initialize()
    logger.info("open camera")
    device = open_camera()
    logger.success("camera opened")
    try:
        setCameraParams(device)
        logger.info("set camera params")
        setCameraParams(device)
        logger.success("camera params set")
        logger.info("start acquisition")
        node_map_remote_device = device.RemoteDevice().NodeMaps()[0]
        node_map_remote_device.FindNode("UserSetSelector").SetCurrentEntry("Default")
        node_map_remote_device.FindNode("UserSetLoad").Execute()
        # node_map_remote_device.FindNode("TriggerSelector").SetCurrentEntry("ReadOutStart")
        self.node_map_remote_device.FindNode("GainAuto").SetCurrentEntry("Continuous")
        self.node_map_remote_device.FindNode("ExposureAuto").SetCurrentEntry("Off")
        self.node_map_remote_device.FindNode("ExposureTime").SetValue(18000)
        node_map_remote_device.FindNode("TriggerMode").SetCurrentEntry("On")
        node_map_remote_device.FindNode("TriggerSource").SetCurrentEntry("Software")
        logger.success("acquisition setup done")


        datastreams = device.DataStreams()
        if datastreams.empty():
            device = None
            exit(-1)
        datastream = datastreams[0].OpenDataStream()
        if datastream:
        # Flush queue and prepare all buffers for revoking
            datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
        # Clear all old buffers
            for buffer in datastream.AnnouncedBuffers():
                datastream.RevokeBuffer(buffer)
            payload_size = node_map_remote_device.FindNode("PayloadSize").Value()
            # Get number of minimum required buffers
            num_buffers_min_required = datastream.NumBuffersAnnouncedMinRequired()
            # Alloc buffers
            for count in range(num_buffers_min_required):
                buffer = datastream.AllocAndAnnounceBuffer(payload_size)
                datastream.QueueBuffer(buffer)

        datastream.StartAcquisition(ids_peak.AcquisitionStartMode_Default, ids_peak.DataStream.INFINITE_NUMBER)
        node_map_remote_device.FindNode("TLParamsLocked").SetValue(1)
        node_map_remote_device.FindNode("AcquisitionStart").Execute()
        filename = makeFileName()
        imageAquisitionThread = threading.Thread(target=imageAquisition, args=(datastream, filename))
        imageAquisitionThread.start()
        triggerThread = threading.Thread(target=trigger, args=(node_map_remote_device,))
        triggerThread.start()

        imageAquisitionThread.join()
        triggerThread.join()
        
        return filename

    except Exception as e:
        print(e)
    logger.info("close camera and library")
    ids_peak.Library.Close()

if __name__ == "__main__":
    a = takePicture()
    print(a)