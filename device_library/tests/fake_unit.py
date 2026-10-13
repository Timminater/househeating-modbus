"""In-memory ModbusUnit test double. No networking or frame simulation."""
import asyncio


def memory(divisor=10, measurement_divisor=10, protocol=130):
    data = {}
    for start, count in ((0, 10), (0x40, 30), (0x300, 8), (0x360, 4),
                         (0x313, 4), (0x72, 12), (0x19, 8)):
        data.update({a: 0 for a in range(start, start + count)})
    for a in range(0x47, 0x53):
        data[a] = int(30 * measurement_divisor)
    data.update({0x40: 35, 0x41: 600, 0x44: 230, 0x45: 42, 0x46: 50,
                 0x4A: int(8 * measurement_divisor), 0x4F: int(28 * measurement_divisor),
                 0x50: int(32 * measurement_divisor), 0x54: int(50 * measurement_divisor),
                 0x58: 123, 0x5C: 257, 0x74: int(31 * measurement_divisor),
                 0x300: 12 * divisor, 0x301: 35 * divisor, 0x302: 55 * divisor,
                 0x303: 35 * divisor, 0x304: 7, 0x305: 1, 0x306: 20 * divisor,
                 0x307: 0, 0x360: 404, 0x361: 0, 0x362: 1, 0x363: protocol})
    return data


class FakeUnit:
    def __init__(self, data=None):
        self.data = memory() if data is None else data
        self.connected = True
        self.reads = []
        self.writes = []
        self.spacing = None
        self.timeout = None
        self.fail_addresses = set()
        self.bad_payload = None
        self.drop_write = False
        self.ack_error = False
        self.callback = None
        self.delay = 0
        self.active = 0
        self.max_active = 0

    def set_message_spacing(self, seconds):
        self.spacing = seconds

    def require_timeout(self, seconds):
        self.timeout = seconds

    def on_connection_lost(self, callback):
        self.callback = callback
        def unsubscribe():
            self.callback = None
        return unsubscribe

    async def read_holding_registers(self, address, count):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            self.reads.append((address, count))
            if any(a in self.fail_addresses for a in range(address, address + count)):
                raise TimeoutError("simulated timeout")
            if self.bad_payload is not None:
                return self.bad_payload
            self.connected = True
            return [self.data[a] for a in range(address, address + count)]
        finally:
            self.active -= 1

    async def write_register(self, address, value):
        await asyncio.sleep(self.delay)
        self.writes.append((address, value))
        if not self.drop_write:
            self.data[address] = value
        if self.ack_error:
            raise TimeoutError("acknowledgement lost")
