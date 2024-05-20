from typing import TypedDict

class USBIdentity(TypedDict):
  product: int
  vendor: int

__all__ = [
  'USBIdentity'
]