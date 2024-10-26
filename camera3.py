import sys

from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak import ids_peak_ipl_extension

FPS_LIMIT = 30
TARGET_PIXEL_FORMAT = ids_peak_ipl.PixelFormatName_RGB8

class IdsCamera:
    def __init__(self):
        self.__device = None
        self.__nodemap_remote_device = None
        self.__datastream = None
        self.__acquisition_running = False
        self.__image_converter = ids_peak_ipl.ImageConverter()

        ids_peak.Library.Initialize()

        if self.__open_device():
            try:
                # Create a display for the camera image
                if not self.__start_acquisition():
                    print("Error", "Unable to start acquisition!")
            except Exception as e:
                print("Exception", str(e))

    def __open_device(self):    
        try:
            # Create instance of the device manager
            device_manager = ids_peak.DeviceManager.Instance()
            
            # Update the device manager
            device_manager.Update()
            
            # Return if no device was found
            if device_manager.Devices().empty():
                print("Error", "No device found!")
                return False

            # Open the first openable device in the managers device list
            for device in device_manager.Devices():
                if device.IsOpenable():
                    self.__device = device.OpenDevice(ids_peak.DeviceAccessType_Control)
                    break
            # Return if no device could be opened
            if self.__device is None:
                print("Error", "Device could not be opened!")
                return False

            # Open standard data stream
            datastreams = self.__device.DataStreams()
            
            if datastreams.empty():
                print("Error", "Device has no DataStream!")
                self.__device = None
                return False

            self.__datastream = datastreams[0].OpenDataStream()
            
            # Get nodemap of the remote device for all accesses to the genicam nodemap tree
            self.__nodemap_remote_device = self.__device.RemoteDevice().NodeMaps()[0]
            
            # To prepare for untriggered continuous image acquisition, load the default user set if available and
            # wait until execution is finished
            try:
                self.__nodemap_remote_device.FindNode("UserSetSelector").SetCurrentEntry("Default")
                self.__nodemap_remote_device.FindNode("UserSetLoad").Execute()
                self.__nodemap_remote_device.FindNode("UserSetLoad").WaitUntilDone()
                
            except ids_peak.Exception:
                # Userset is not available
                print("Warning", "Userset is not available")
                pass
            

            # Get the payload size for correct buffer allocation
            payload_size = self.__nodemap_remote_device.FindNode("PayloadSize").Value()
            
            # Get minimum number of buffers that must be announced
            buffer_count_max = self.__datastream.NumBuffersAnnouncedMinRequired()
            
            # Allocate and announce image buffers and queue them
            for i in range(buffer_count_max):
                buffer = self.__datastream.AllocAndAnnounceBuffer(payload_size)
                self.__datastream.QueueBuffer(buffer)
            
            return True
        except ids_peak.Exception as e:
            print("Exception", str(e))

        return False

    def __close_device(self):
        """
        Stop acquisition if still running and close datastream and nodemap of the device
        """
        # Stop Acquisition in case it is still running
        self.__stop_acquisition()

        # If a datastream has been opened, try to revoke its image buffers
        if self.__datastream is not None:
            try:
                for buffer in self.__datastream.AnnouncedBuffers():
                    self.__datastream.RevokeBuffer(buffer)
            except Exception as e:
                print("Exception", str(e))

    def __start_acquisition(self):
        """
        Start Acquisition on camera and start the acquisition timer to receive and display images

        :return: True/False if acquisition start was successful
        """
        # Check that a device is opened and that the acquisition is NOT running. If not, return.
        if self.__device is None:
            return False
        if self.__acquisition_running is True:
            return True

        # Get the maximum framerate possible, limit it to the configured FPS_LIMIT. If the limit can't be reached, set
        # acquisition interval to the maximum possible framerate
        try:
            max_fps = self.__nodemap_remote_device.FindNode("AcquisitionFrameRate").Maximum()
            target_fps = min(max_fps, FPS_LIMIT)
            self.__nodemap_remote_device.FindNode("AcquisitionFrameRate").SetValue(target_fps)
        except ids_peak.Exception:
            # AcquisitionFrameRate is not available. Unable to limit fps. Print warning and continue on.
            print("Warning", "Unable to limit fps, since the AcquisitionFrameRate Node is"
                                " not supported by the connected camera. Program will continue without limit.")

        try:
            # Lock critical features to prevent them from changing during acquisition
            self.__nodemap_remote_device.FindNode("TLParamsLocked").SetValue(1)

            image_width = self.__nodemap_remote_device.FindNode("Width").Value()
            image_height = self.__nodemap_remote_device.FindNode("Height").Value()
            input_pixel_format = ids_peak_ipl.PixelFormat(
                self.__nodemap_remote_device.FindNode("PixelFormat").CurrentEntry().Value())

            # Pre-allocate conversion buffers to speed up first image conversion
            # while the acquisition is running
            # NOTE: Re-create the image converter, so old conversion buffers
            #       get freed
            self.__image_converter = ids_peak_ipl.ImageConverter()
            self.__image_converter.PreAllocateConversion(
                input_pixel_format, TARGET_PIXEL_FORMAT,
                image_width, image_height)

            # Start acquisition on camera
            self.__datastream.StartAcquisition()
            self.__nodemap_remote_device.FindNode("AcquisitionStart").Execute()
            self.__nodemap_remote_device.FindNode("AcquisitionStart").WaitUntilDone()
        except Exception as e:
            print("Exception: " + str(e))
            return False

        # Start acquisition timer
        self.__acquisition_running = True

        return True

    def __stop_acquisition(self):
        """
        Stop acquisition timer and stop acquisition on camera
        :return:
        """
        # Check that a device is opened and that the acquisition is running. If not, return.
        if self.__device is None or self.__acquisition_running is False:
            return

        # Otherwise try to stop acquisition
        try:
            remote_nodemap = self.__device.RemoteDevice().NodeMaps()[0]
            remote_nodemap.FindNode("AcquisitionStop").Execute()

            # Stop and flush datastream
            self.__datastream.KillWait()
            self.__datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            self.__datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)

            self.__acquisition_running = False

            # Unlock parameters after acquisition stop
            if self.__nodemap_remote_device is not None:
                try:
                    self.__nodemap_remote_device.FindNode("TLParamsLocked").SetValue(0)
                except Exception as e:
                    print("Exception", str(e))

        except Exception as e:
            print("Exception", str(e))
            
    def streaming_image(self):
        try:
            # Get buffer from device's datastream
            buffer = self.__datastream.WaitForFinishedBuffer(5000)
            # Create IDS peak IPL image for debayering and convert it to RGBa8 format
            ipl_image = ids_peak_ipl_extension.BufferToImage(buffer)
            converted_ipl_image = self.__image_converter.Convert(
                ipl_image, TARGET_PIXEL_FORMAT)
            # Convert IDS peak IPL image to numpy array
            img = converted_ipl_image.get_numpy_3D()

            self.__datastream.QueueBuffer(buffer)

            yield img
            
        except ids_peak.Exception as e:
            print("Exception: " + str(e))

    def __del__(self):
        self.__destroy_all()

    def __destroy_all(self):
        # Stop acquisition
        self.__stop_acquisition()

        # Close device and peak library
        self.__close_device()
        ids_peak.Library.Close()


if __name__ == "__main__":
    camera = IdsCamera()
    
