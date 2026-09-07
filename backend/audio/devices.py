from __future__ import annotations

import sys


def list_loopback_devices() -> list[dict]:
    devices = [
        {"id": "system_default_loopback", "name": "Default loopback", "is_loopback": True}
    ]
    if sys.platform == "win32":
        devices.extend(_list_soundcard_loopbacks())
        devices.extend(_list_wasapi_loopbacks())
        devices.extend(_list_sounddevice_loopbacks())
    else:
        devices.extend(_list_sounddevice_loopbacks())
    return devices


def _list_soundcard_loopbacks() -> list[dict]:
    try:
        import soundcard as sc
    except ImportError:
        return []
    found: list[dict] = []
    try:
        for mic in sc.all_microphones(include_loopback=True):
            if not getattr(mic, "isloopback", False):
                continue
            found.append({"id": str(mic.id), "name": mic.name, "is_loopback": True})
    except Exception:
        return found
    return found


def _list_wasapi_loopbacks() -> list[dict]:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        return []
    pa = pyaudio.PyAudio()
    found: list[dict] = []
    try:
        for device in pa.get_loopback_device_info_generator():
            found.append(
                {
                    "id": str(device["index"]),
                    "name": device["name"],
                    "is_loopback": True,
                }
            )
    except Exception:
        return found
    finally:
        pa.terminate()
    return found


def _list_sounddevice_loopbacks() -> list[dict]:
    try:
        import sounddevice as sd
    except ImportError:
        return []
    markers = ("blackhole", "loopback", "monitor", "stereo mix", "cable")
    found: list[dict] = []
    try:
        for index, device in enumerate(sd.query_devices()):
            name = str(device.get("name", ""))
            is_loopback = any(token in name.lower() for token in markers)
            if is_loopback:
                found.append(
                    {
                        "id": index,
                        "name": name,
                        "is_loopback": True,
                    }
                )
    except Exception:
        return found
    return found
