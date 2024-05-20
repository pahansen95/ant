### Modified USB Driver

import \
  usb.util, usb.core, \
  openant.base.commons, openant.base.driver, \
  logging, time, collections.abc

class USBDriver(openant.base.driver.Driver):  
  ### Custom Attributes
  _logger = logging.getLogger("openant.base.driver")

  ### Attribute Inheritance

  read = openant.base.driver.USBDriver.read
  write = openant.base.driver.USBDriver.write

  ### Attribute Compatibility Overrides

  @property
  def ID_VENDOR(self): return self.dev.idVendor
  @property
  def ID_PRODUCT(self): return self.dev.idProduct
  def find(self, **kwargs): return True

  ### Attribute Custom Overrides
  def __init__(self, device: usb.core.Device):
    self.dev = device
    self._in = None
    self._out = None

  def open(self):

    self._logger.debug(f"Using USB Device: {self.ID_PRODUCT}:{self.ID_VENDOR}")

    self._logger.debug(f"USB Config values...\n{self.dev}")
    # for cfg in self.dev:
    #   self._logger.debug(" Config %s", cfg.bConfigurationValue)
    #   for intf in cfg:
    #     self._logger.debug(
    #       "  Interface %s, Alt %s",
    #       str(intf.bInterfaceNumber),
    #       str(intf.bAlternateSetting),
    #     )
    #     for ep in intf:
    #       self._logger.debug("   Endpoint %s", str(ep.bEndpointAddress))

    # # unmount a kernel driver (TODO: should probably reattach later)
    # try:
    #   if self.dev.is_kernel_driver_active(0):
    #     self._logger.debug("A kernel driver active, detatching")
    #     self.dev.detach_kernel_driver(0)
    #   else:
    #     self._logger.debug("No kernel driver active")
    # except NotImplementedError as e:
    #   self._logger.warning(
    #       "Could not check if kernel driver was active, not implemented in usb backend"
    #   )

    # set the active configuration. With no arguments, the first
    # configuration will be the active one
    self.dev.set_configuration()
    try:
      self.dev.reset()
    except NotImplementedError as _:
      self._logger.warning(
          "Could not reset the device, not implemented in usb backend"
      )
    if openant.base.commons.is_windows():
      time.sleep(2)

    # get an endpoint instance
    cfg = self.dev.get_active_configuration()
    intf = cfg[(0, 0)]

    self._out = usb.util.find_descriptor(
      intf,
      # match the first OUT endpoint
      custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
      == usb.util.ENDPOINT_OUT,
    )

    self._logger.debug(
      "USB Endpoint out: %s, %s", self._out, self._out.bEndpointAddress
    )

    self._in = usb.util.find_descriptor(
      intf,
      # match the first OUT endpoint
      custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
      == usb.util.ENDPOINT_IN,
    )

    self._logger.debug(
      "USB Endpoint in: %s, %s", self._in, self._in.bEndpointAddress
    )

    assert self._out is not None and self._in is not None

  def close(self):
    self._logger.debug("Skipping USB Device Close: not supported in Monkey Patch")


### Modified ANT Device
import openant.base.ant, threading, collections, queue, array
class AntTransceiverDevice(openant.base.ant.Ant):
  
  def __init__(self, driver: USBDriver):
    self._driver = driver

    self._message_queue_cond = threading.Condition()
    self._message_queue = collections.deque()

    self._events = queue.Queue()

    self._buffer = array.array("B", [])
    self._burst_data = array.array("B", [])
    self._last_data = array.array("B", [])

    self._running = True

    self._driver.open()

    self._worker_thread = threading.Thread(target=self._worker, name="openant.base")
    self._worker_thread.start()

    self.reset_system()

### Modified ANT Easy Node
import openant.easy.node, openant.easy.channel, openant.easy.filter
from typing import Optional, List
class AntTransceiver(openant.easy.node.Node):
  def __init__(self, ant: AntTransceiverDevice):

    self._responses_cond = threading.Condition()
    self._responses = collections.deque()
    self._event_cond = threading.Condition()
    self._events = collections.deque()

    self._datas = queue.Queue()

    # will replace with response from node at open
    self.serial: Optional[int] = None
    self.ant_version: Optional[str] = None
    self.max_networks = 8
    self.max_channels = 8
    self.channels: List[openant.easy.channel.Channel] = []
    self.standard_options = set()
    self.advanced_options = set()
    self.advanced_options_two = set()
    self.advanced_options_three = set()
    self.max_sensorcore_channels = 0

    self.ant = ant

    self._running = True

    self._worker_thread = threading.Thread(target=self._worker, name="openant.easy")
    self._worker_thread.start()

  @property
  def transceiver(self) -> AntTransceiverDevice:
    return self.ant

__all__ = [] # Don't export anything