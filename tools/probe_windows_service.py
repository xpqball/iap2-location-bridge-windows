"""Bounded USB/CarKit connectivity probe; no authentication or location data."""

import asyncio

from pymobiledevice3.lockdown import create_using_usbmux


async def probe():
    phone = await create_using_usbmux(connection_type="USB", autopair=False)
    try:
        print("USB lockdown connected", flush=True)
        stream = await phone.start_lockdown_service("com.apple.carkit.service")
        try:
            print("CarKit service opened successfully", flush=True)
        finally:
            await stream.close()
    finally:
        await phone.close()


async def main():
    try:
        await asyncio.wait_for(probe(), timeout=30)
    except Exception as error:
        # Avoid printing device identifiers or pairing records in shared logs.
        print(f"Probe failed: {type(error).__name__}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
