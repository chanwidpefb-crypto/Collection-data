"""Modbus register <-> value conversion.

Handles the data types and word/byte orderings ("ABCD" style) that show up on
real Modbus devices. A value that spans multiple 16-bit registers can be laid
out on the wire in four common orders:

    ABCD  big-endian words, big-endian bytes within each word (Modbus standard)
    BADC  big-endian words, byte-swapped within each word
    CDAB  word-swapped, big-endian bytes within each word ("word swap")
    DCBA  word-swapped and byte-swapped (little-endian)

`decode_registers` / `encode_value` are exact inverses of each other for every
(data_type, word_order) combination, which is what the unit tests check.
"""
from __future__ import annotations

import struct
from enum import Enum


class DataType(str, Enum):
    BOOL = "bool"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"
    INT64 = "int64"
    UINT64 = "uint64"
    FLOAT64 = "float64"


class WordOrder(str, Enum):
    ABCD = "ABCD"
    BADC = "BADC"
    CDAB = "CDAB"
    DCBA = "DCBA"


# struct format char (big-endian) for each data type
_STRUCT_FMT = {
    DataType.INT16: "h",
    DataType.UINT16: "H",
    DataType.INT32: "i",
    DataType.UINT32: "I",
    DataType.FLOAT32: "f",
    DataType.INT64: "q",
    DataType.UINT64: "Q",
    DataType.FLOAT64: "d",
}


def register_count(data_type: DataType | str) -> int:
    """Number of 16-bit registers a value of this data type occupies."""
    data_type = DataType(data_type)
    if data_type == DataType.BOOL:
        return 1
    return struct.calcsize(_STRUCT_FMT[data_type]) // 2


def _byte_swap16(word: int) -> int:
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


def decode_registers(registers: list[int], data_type: DataType | str,
                      word_order: WordOrder | str = WordOrder.ABCD) -> float | int | bool:
    """Convert raw 16-bit register values (in address order) into a value."""
    data_type = DataType(data_type)
    word_order = WordOrder(word_order)

    if data_type == DataType.BOOL:
        return bool(registers[0])

    expected = register_count(data_type)
    if len(registers) != expected:
        raise ValueError(
            f"{data_type.value} needs {expected} register(s), got {len(registers)}"
        )

    word_swap = word_order in (WordOrder.CDAB, WordOrder.DCBA)
    byte_swap = word_order in (WordOrder.BADC, WordOrder.DCBA)

    ordered = list(reversed(registers)) if word_swap else list(registers)
    words_be = [_byte_swap16(w) if byte_swap else w for w in ordered]

    raw = b"".join(struct.pack(">H", w & 0xFFFF) for w in words_be)
    (value,) = struct.unpack(">" + _STRUCT_FMT[data_type], raw)
    return value


def encode_value(value: float | int | bool, data_type: DataType | str,
                  word_order: WordOrder | str = WordOrder.ABCD) -> list[int]:
    """Convert a value into raw 16-bit register values (in address order)."""
    data_type = DataType(data_type)
    word_order = WordOrder(word_order)

    if data_type == DataType.BOOL:
        return [1 if value else 0]

    word_swap = word_order in (WordOrder.CDAB, WordOrder.DCBA)
    byte_swap = word_order in (WordOrder.BADC, WordOrder.DCBA)

    fmt = _STRUCT_FMT[data_type]
    if data_type in (DataType.INT16, DataType.UINT16, DataType.INT32, DataType.UINT32,
                      DataType.INT64, DataType.UINT64):
        value = int(round(value))
        lo, hi = _int_range(data_type)
        if not (lo <= value <= hi):
            raise ValueError(f"{value} out of range for {data_type.value} ({lo}..{hi})")
    raw = struct.pack(">" + fmt, value)

    words_be = [struct.unpack(">H", raw[i:i + 2])[0] for i in range(0, len(raw), 2)]
    transformed = [_byte_swap16(w) if byte_swap else w for w in words_be]
    return list(reversed(transformed)) if word_swap else transformed


def _int_range(data_type: DataType) -> tuple[int, int]:
    bits = register_count(data_type) * 16
    if data_type.value.startswith("u"):
        return 0, (1 << bits) - 1
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
