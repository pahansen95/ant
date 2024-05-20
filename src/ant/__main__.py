from __future__ import annotations
import os, sys, orjson, time
from typing import TypedDict, Optional, NotRequired
from collections.abc import Generator
from usb.core import Device as USBDevice
from openant.devices import ANTPLUS_NETWORK_KEY
import openant.devices.common, openant.devices.scanner
from loguru import logger

### Local Imports
import ant
###

ANT_TRANSCEIVERS: dict[str, ant.USBIdentity] = {
  "ANT USB-M Transceiver": {
    "product": 0x1009,
    "vendor": 0x0fcf,
  }
}

def scan_for_clients(
  identity: ant.USBIdentity,
  libusb1_path: str | None = None
) -> int:
  logger.info("Scanning for ANT+ Client Devices")
  usb_dev, ant_trancvr, client_scanner = None, None, None
  try:
    usb_dev, ant_trancvr = ant.setup_transceiver(identity, libusb1_path)
    client_scanner = ant.setup_scanner(ant_trancvr)
    ant_trancvr.start()
  except KeyboardInterrupt:
    logger.warning("User Requested Teardown")
  finally:
    try: ant.teardown_scanner(client_scanner)
    except Exception as e: logger.warning(f"Failed to stop the ANT+ Client Scanner: {e}")
    try: ant.teardown_transceiver(usb_dev, ant_trancvr)
    except Exception as e: logger.warning(f"Failed to teardown the ANT+ Transceiver: {e}")
  
  logger.success("Scan Complete")
  return 0

def read_client(
  identity: ant.USBIdentity,
  client: ant.ClientID,
  libusb1_path: str | None = None,
):
  logger.info(f"Reading Data from ANT+ Client Device...\n{ant.ClientID.render(client)}")
  usb_dev, ant_trancvr, device = None, None, None
  try:
    usb_dev, ant_trancvr = ant.setup_transceiver(identity, libusb1_path)

    ### Create the ANT+ Client Device Based on the Type
    dev_type = openant.devices.common.DeviceType(client['device_type'])
    if dev_type == openant.devices.common.DeviceType.HeartRate:
      device = openant.devices.heart_rate.HeartRate(ant_trancvr, client['device_id'], client['transmission_type'])
      last_beat_idx = -1
      datum: int = time.monotonic_ns()
      def _log_data(page: int, page_name: str, data: openant.devices.heart_rate.HeartRateData):
        nonlocal last_beat_idx
        assert isinstance(data, openant.devices.heart_rate.HeartRateData)
        metadata: ant.Metadata = {
          "time": {
            "unit": 'ns',
            "datum": datum,
            "diff": time.monotonic_ns() - datum,
          }
        }
        logger.debug(f"Received ANT+ Heart Rate Data: {data}")
        if last_beat_idx == data.beat_count: return
        last_beat_idx = data.beat_count
        sys.stdout.buffer.write(
          orjson.dumps(
            ant.HeartRateSpec.from_data(data, metadata),
            # { 'kind': 'heart_rate', 'metadata': { 'diff_ns': (time.monotonic_ns() - datum) }, 'data': {'bpm': data.heart_rate, 'beat': data.beat_count, 'time': {'cur': data.beat_time, 'prev': data.previous_heart_beat_time }}},
            # {"heart_rate_bpm": data.heart_rate, "heart_beat": { 'count': data.beat_count, 'cur': data.beat_time, 'prev': data.previous_heart_beat_time}},
            option=orjson.OPT_APPEND_NEWLINE,
          )
        )
        sys.stdout.flush()
      device.on_device_data = _log_data
    else:
      CLIError(f"Unsupported Device Type: {dev_type}")

    logger.info("Starting the ANT+ Transceiver; press Ctrl-C to exit")
    ant_trancvr.start()
  except KeyboardInterrupt:
    logger.warning("User Requested Teardown")
  finally:
    if device is not None:
      try: device.close_channel()
      except Exception as e: logger.warning(f"Failed to stop the ANT+ Client Channel: {e}")
    try: ant.teardown_transceiver(usb_dev, ant_trancvr)
    except Exception as e: logger.warning(f"Failed to teardown the ANT+ Transceiver: {e}")

def main(args: tuple[str, ...], kwargs: CLI_KWARGS) -> int:
  if len(args) < 1: raise CLIError("Missing subcommand")
  subcmd = args[0]
  if subcmd == 'scan':
    return scan_for_clients(ANT_TRANSCEIVERS[kwargs['transceiver']], kwargs['libusb1'])
  elif subcmd == 'read':
    if len(args) > 1:
      if args[1] == '-': client_cfg = orjson.loads(sys.stdin.read())
      else: client_cfg = orjson.loads(args[1])
    else: client_cfg = orjson.loads(sys.stdin.read())
    return read_client(ANT_TRANSCEIVERS[kwargs['transceiver']], {
      "device_id": client_cfg['id'],
      "device_type": client_cfg['type'],
      "transmission_type": client_cfg['txn'],
    }, kwargs['libusb1'])
  else:
    raise CLIError(f"Unknown subcommand: {subcmd}")


  logger.info("Finding the `ANT USB-M Transceiver` USB Device")
  usb_dev: Generator[USBDevice] | USBDevice = None
  try:
    if 'LIBUSB1_PATH' in os.environ:
      logger.debug(f"Using custom libusb1 path: {os.environ['LIBUSB1_PATH']}")
      # See https://github.com/pyusb/pyusb/blob/master/docs/tutorial.rst#specifying-libraries-by-hand
      import usb.core, usb.backend.libusb1
      backend = usb.backend.libusb1.get_backend(find_library=lambda x: os.environ['LIBUSB1_PATH'])
      usb_dev = usb.core.find(**USB_DEVICES["ANT USB-M Transceiver"], backend=backend)
    else:
      logger.debug("Searching for an available USB Backend")
      import usb.core
      usb_dev = usb.core.find(**USB_DEVICES["ANT USB-M Transceiver"])
    
    if usb_dev is None: raise Exception("Unexpected Error: Failed to set a device")
  except Exception as e:
    raise CLIError(f"Couldn't find the `ANT USB-M Transceiver` USB Device: ({type(e).__name__}) {e}")
  
  logger.success("Found the `ANT USB-M Transceiver` USB Device")
  if isinstance(usb_dev, Generator):
    logger.debug("Multiple devices found, using the first one")
    usb_dev = next(usb_dev)
  assert isinstance(usb_dev, USBDevice)
  logger.debug(f"Found USB Device...\n{usb_dev}")

  device_driver: _patch.USBDriver = None
  transceiver: _patch.AntTransceiver = None
  client_scanner: openant.devices.scanner.Scanner = None
  try:
    logger.info("Setting up ANT Transceiver USB Driver")
    device_driver = _patch.USBDriver(usb_dev)
    logger.info("Setting up ANT Transceiver")
    transceiver = _patch.AntTransceiver(_patch.AntTransceiverDevice(device_driver))
    transceiver.set_network_key(0x00, ANTPLUS_NETWORK_KEY)
    logger.info("Setting up ANT Client Scanner")
    client_scanner = openant.devices.scanner.Scanner(transceiver)
    client_scanner.on_found = ANTClientDevice.on_found
    client_scanner.on_update = ANTClientDevice.on_update
    logger.info("Starting the ANT+ Transceiver; press Ctrl-C to exit")
    transceiver.start()
  except KeyboardInterrupt:
    logger.info("Closing ANT+ Node")
  finally:
    if client_scanner is not None:
      try:
        client_scanner.close_channel()
      except:
        logger.opt(exception=True).warning("Failed to stop the ANT+ Client Scanner")
    if transceiver is not None:
      try:
        transceiver.stop()
      except:
        logger.opt(exception=True).warning("Failed to stop the ANT+ Node")
    if device_driver is not None:
      try:
        device_driver.close()
      except:
        logger.opt(exception=True).warning("Failed to close the USB Device")
  
  logger.success("Finished")
  return 0

class CLIError(RuntimeError): pass

def setup_logging(log_level: str = os.environ.get('LOG_LEVEL', 'INFO')):
  logger.remove()
  logger.add(sys.stderr, level=log_level, enqueue=True, colorize=True)
  logger.trace(f'Log level set to {log_level}')
  import logging
  _log_level = {
    'TRACE': 'DEBUG',
    'DEBUG': 'DEBUG',
    'INFO': 'INFO',
    'WARNING': 'WARNING',
    'SUCCESS': 'ERROR',
    'ERROR': 'ERROR',
    'CRITICAL': 'CRITICAL'
  }[log_level]
  for _handle in (
    'usb',
    'usb.core',
  ):
    logger.trace(f'Setting log level for {_handle} to {_log_level}')
    _logger = logging.getLogger(_handle)
    _logger.setLevel(_log_level)
    _logger.addHandler(logging.StreamHandler(sys.stderr))

def finalize_logging():
  logger.complete()

class CLI_KWARGS(TypedDict):
  log: str
  libusb1: NotRequired[str]
  transceiver: str

def parse_argv(argv: list[str], env: dict[str, str]) -> tuple[tuple[str, ...], CLI_KWARGS]:
  args = []
  kwargs = {
    "log": env.get('LOG_LEVEL', 'INFO'),
    "libusb1": env.get('LIBUSB1_PATH', None),
    "transceiver": env.get('ANT_TRANSCEIVER', "ANT USB-M Transceiver"),
  }
  for idx, arg in enumerate(argv):
    if arg == '--':
      logger.trace(f"Found end of arguments at index {idx}")
      args.extend(argv[idx+1:])
      break
    elif arg.startswith('--'):
      logger.trace(f"Found keyword argument: {arg}")
      if '=' in arg: key, value = arg[2:].split('=', 1)
      else: key, value = arg[2:], True
      kwargs[key] = value
    else:
      logger.trace(f"Found positional argument: {arg}")
      args.append(arg)
  return tuple(args), kwargs

if __name__ == '__main__':
  setup_logging()
  _rc = 255
  try:
    logger.trace(f"Arguments: {sys.argv[1:]}\nEnvironment: {os.environ}")
    args, kwargs = parse_argv(sys.argv[1:], os.environ)
    logger.trace(f"Arguments: {args}\nKeywords: {kwargs}")
    setup_logging(kwargs['log']) # Reconfigure logging
    logger.trace(f"Log level set to {kwargs['log']}")
    _rc = main(args, kwargs)
  except CLIError as e:
    logger.error(str(e))
    _rc = 2
  except:
    logger.opt(exception=True).critical('Unhandled exception')
    _rc = 3
  finally:
    finalize_logging()
    sys.stdout.flush()
    sys.stderr.flush()
  exit(_rc)