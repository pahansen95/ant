from __future__ import annotations
from loguru import logger
from typing import TypedDict, NotRequired, Literal
from collections.abc import Generator, Callable

import usb.core, usb.backend.libusb1
import openant.devices, openant.devices.scanner, openant.easy

### Package Imports
from .usb import USBIdentity
from . import monkeypatches as _patch
###

class ScannerCallbacks(TypedDict):
  on_found: NotRequired[Callable[[tuple[int, int, int]], None]]
  on_update: NotRequired[Callable[[tuple[int, int, int], openant.devices.common.CommonData], None]]

class _DefaultScannerCallbacks:

  @staticmethod
  def on_found(device_tuple: tuple[int, int, int]) -> None:
    chan_idnt: ClientID = {"device_id": device_tuple[0], "device_type": device_tuple[1], "transmission_type": device_tuple[2]}
    logger.debug(f"Found new Client Device...\n{ClientID.render(chan_idnt)}")

  @staticmethod
  def on_update(device_tuple: tuple[int, int, int], common: openant.devices.common.CommonData) -> None:
    chan_idnt: ClientID = {"device_id": device_tuple[0], "device_type": device_tuple[1], "transmission_type": device_tuple[2]}
    logger.debug(f"Client Device Updated Common Data...\n{ClientID.render(chan_idnt)}\n  common_data: {common}")

DEFAULT_SCANNER_CALLBACKS: ScannerCallbacks = {
  "on_found": _DefaultScannerCallbacks.on_found,
  "on_update": _DefaultScannerCallbacks.on_update
}

### ANT+ Transceiver

def teardown_transceiver(
  usb_driver: _patch.USBDriver | None,
  transceiver: _patch.AntTransceiver | None,
) -> None:
  error = ""
  if transceiver is not None:
    try:
      transceiver.stop()
    except Exception as e:
      error += f"Failed to stop the ANT+ Node: {e}"
      logger.opt(exception=e).debug("Failed to stop the ANT+ Node")
  if usb_driver is not None:
    try:
      usb_driver.close()
    except Exception as e:
      error += f"Failed to close the USB Device: {e}"
      logger.opt(exception=e).debug("Failed to close the USB Device")
  
  if error: raise RuntimeError(error)

def setup_transceiver(
  usb_id: USBIdentity,
  libusb1_path: str = None
) -> tuple[_patch.USBDriver, _patch.AntTransceiver]:
  usb_dev: Generator[usb.core.Device] | usb.core.Device = None
  try:
    if libusb1_path is not None:
      logger.debug(f"Using custom libusb1 path: {libusb1_path}")
      # See https://github.com/pyusb/pyusb/blob/master/docs/tutorial.rst#specifying-libraries-by-hand
      backend = usb.backend.libusb1.get_backend(find_library=lambda x: libusb1_path)
      usb_dev = usb.core.find(usb_id, backend=backend)
    else:
      logger.debug("Searching for an available USB Backend")
      usb_dev = usb.core.find(usb_id)
    
    if usb_dev is None: raise Exception("Unexpected Error: Failed to set a device")
  except Exception as e:
    raise RuntimeError(f"Couldn't find the `ANT USB-M Transceiver` USB Device: ({type(e).__name__}) {e}")
  
  logger.success("Found the `ANT USB-M Transceiver` USB Device")
  if isinstance(usb_dev, Generator):
    _devs = list(usb_dev)
    if len(_devs) > 1:
      logger.debug("Multiple devices found, using the first one")
      usb_dev = _devs[0]
  assert isinstance(usb_dev, usb.core.Device)
  logger.debug(f"Found USB Device...\n{usb_dev}")
  usb_dev.set_configuration()

  usb_driver: _patch.USBDriver = None
  transceiver: _patch.AntTransceiver = None

  try:
    logger.debug("Setting up ANT Transceiver USB Driver")
    usb_driver = _patch.USBDriver(usb_dev)
    logger.debug("Setting up ANT Transceiver")
    transceiver = _patch.AntTransceiver(_patch.AntTransceiverDevice(usb_driver))
    transceiver.set_network_key(0x00, openant.devices.ANTPLUS_NETWORK_KEY)
  except Exception as e:
    logger.debug("Some Error encountered while setting up the Transceiver; will teardown")
    try: teardown_transceiver(usb_driver, transceiver)
    except Exception as ee: logger.opt(exception=ee).debug("Failed to teardown the ANT Transceiver")
    raise RuntimeError("Failed to setup the ANT Transceiver") from e
  
  return usb_driver, transceiver

### ANT+ Client ID

class ClientID(TypedDict):
  device_id: int
  device_type: int
  transmission_type: int

  @staticmethod
  def render(identity: ClientID, prefix: str = '  ') -> str:
    return '\n'.join([
      f"{prefix}device_id: 0x{identity['device_id']:04X}",
      f"{prefix}device_type: 0x{identity['device_type']:04X} ({openant.devices.common.DeviceType(identity['device_type']).name})",
      f"{prefix}transmission_type: 0x{identity['transmission_type']:04X}",
    ])


### ANT+ Client Scanner

def on_found(device_tuple: tuple[int, int, int]) -> None:
  device_id, device_type, device = device_tuple
  logger.debug(f"Found new device `{device_id:04X}` {openant.devices.common.DeviceType(device_type)}; device_type: {device_type}, transmission_type: {device}")

def teardown_scanner(
  client_scanner: openant.devices.scanner.Scanner | None
) -> None:
  if client_scanner is None: return
  error = ""
  try:
    client_scanner.close_channel()
  except Exception as e:
    error += f"Failed to stop the ANT Client Scanner: {e}"
    logger.opt(exception=True).debug("Failed to stop the ANT Client Scanner")
  if error: raise RuntimeError(error)

def setup_scanner(
  transceiver: _patch.AntTransceiver,
  callbacks: ScannerCallbacks = DEFAULT_SCANNER_CALLBACKS,
) -> openant.devices.scanner.Scanner:
  client_scanner: openant.devices.scanner.Scanner = None
  try:
    logger.debug("Setting up ANT Client Scanner")
    client_scanner = openant.devices.scanner.Scanner(
      transceiver,
    )
    if 'on_found' in callbacks: client_scanner.on_found = callbacks["on_found"]
    if 'on_update' in callbacks: client_scanner.on_update = callbacks["on_update"]
  except Exception as e:
    logger.debug("Some Error encountered while setting up the Client Scanner; will teardown")
    try: teardown_scanner(client_scanner)
    except Exception as ee: logger.opt(exception=ee).debug("Failed to teardown the ANT Client Scanner")
    raise RuntimeError("Failed to setup the ANT Client Scanner") from e

### Data Schemas

class Metadata(TypedDict):
  time: Metadata.Time

  class Time(TypedDict):
    unit: Literal["ns"]
    datum: int
    diff: int

class HeartRateSpec(TypedDict):
  kind: Literal["heart_rate"]
  metadata: Metadata
  data: HeartRateSpec.Data

  @staticmethod
  def from_data(data: openant.devices.heart_rate.HeartRateData, metadata: Metadata) -> HeartRateSpec:
    return {
      "kind": "heart_rate",
      "metadata": metadata,
      "data": {
        "bpm": data.heart_rate,
        "beat": data.beat_count,
        "time": {
          "cur": data.beat_time,
          "prev": data.previous_heart_beat_time
        }
      }
    }

  class BeatTime(TypedDict):
    cur: float
    prev: float

  class Data(TypedDict):
    bpm: int
    beat: int
    time: HeartRateSpec.BeatTime

__all__ = [
  "USBIdentity",
  "setup_transceiver", "teardown_transceiver",
  "ScannerCallbacks", "DEFAULT_SCANNER_CALLBACKS",
  "setup_scanner", "teardown_scanner",
  "ClientID",
  "HeartRateSpec", "Metadata",
]