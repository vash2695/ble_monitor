import unittest
from custom_components.ble_monitor.ble_parser.uni_t import parse_uni_t
from custom_components.ble_monitor.ble_parser import BleParser
import logging

# Configure logging to capture debug messages for the test
# This basicConfig is for the test environment. The actual component might have its own logging setup.
logger = logging.getLogger("custom_components.ble_monitor.ble_parser.uni_t")
logger.setLevel(logging.DEBUG)
# Adding a handler if no handlers are configured (e.g., when running tests directly)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.DEBUG)


class TestUniTParser(unittest.TestCase):

    def test_uni_t_ut363bt_valid_data(self):
        # Simulates the BleParser class or necessary parts of it for the test
        # In a real scenario, this might be a mock object or a minimal BleParser instance
        parser_self = BleParser(report_unknown=False, discovery=True, filter_duplicates=False)
        parser_self.rssi = -70 # Example RSSI

        # Sample data construction:
        # mfg[0] = 0x14 (data_len = 20 for type+compid+payload)
        # Total length of mfg array is mfg[0]+1 = 21 bytes.
        # mfg[1] = 0xFF (type)
        # mfg[2:4] = 0xAABB (CompID: LSB AA, MSB BB -> comp_id value 0xBBAA)
        #           comp_id = (mfg[3] << 8) | mfg[2] -> (0xBB << 8) | 0xAA = 0xBBAA
        # pkt = mfg[3] -> 0xBB
        # mfg[4] = 0x00 (skipped byte in current uni_t parser logic for txt)
        # mfg[5:16] = "  2.75M/S50" (wind speed 2.75, unit code 50 = km/h) (11 bytes)
        #             Hex: 2020322E37354D2F533530
        # mfg[16:18] = Temperature 28.3°C (sent as 283, little endian: 1B 01) (2 bytes)
        # mfg[18:21] = Padding (0x000000) (3 bytes for a total of 17 payload bytes)
        
        # Updated sample data based on user provided advertisement:
        # mfg_data_hex = "14ffaabb1005372020312e35324d2f53363080046c"
        # mfg[0] = 0x14 (data_len = 20 for type+compid+payload)
        # mfg[1] = 0xFF (type)
        # mfg[2:4] = 0xAABB (CompID: LSB AA, MSB BB -> comp_id value 0xBBAA)
        # pkt = mfg[3] -> 0xBB
        # mfg[4:9] = 0x1005372020 (skipped bytes by current parser logic for txt)
        # mfg[9:18] = "1.52M/S60" (wind speed 1.52, unit code 60 = ft/min) (9 bytes)
        #             Hex: 312E35324D2F533630
        # mfg[18:20] = Temperature 25.9°C (sent as 1152 (0x0480), little endian: 80 04) (2 bytes)
        #              Calculation: 1152 / 44.5 = 25.8876... -> rounded to 25.9
        # mfg[20] = 0x6C (remaining byte, total 1+2+18 = 21 bytes in mfg, mfg[0]=20)
        
        mfg_data_hex = "14ffaabb1005372020312e35324d2f53363080046c"
        mfg_bytes = bytes.fromhex(mfg_data_hex)
        mac_bytes = bytes.fromhex("112233445566")

        # Capture logs specifically from the uni_t parser's logger
        with self.assertLogs(logger='custom_components.ble_monitor.ble_parser.uni_t', level='DEBUG') as log_watcher:
            data = parse_uni_t(parser_self, mfg_bytes, mac_bytes)

        self.assertIsNotNone(data)
        self.assertEqual(data["type"], "UNI‑T")
        self.assertEqual(data["firmware"], "UT363BT")
        self.assertEqual(data["mac"], "112233445566")

        # Wind speed: 1.52 ft/min. Factor for ft/min (uc 60) is 0.00508
        # Expected speed in m/s = 1.52 * 0.00508 = 0.0077216
        self.assertAlmostEqual(data["wind_speed"], 1.52 * 0.00508, places=5)
        
        # Temperature: 1152 / 44.5 = 25.8876... -> 25.9
        self.assertEqual(data["temperature"], 25.9)
        
        self.assertEqual(data["packet"], 0xBB) # mfg[3] is 0xBB
        self.assertTrue(data["data"])
        self.assertEqual(data["rssi"], -70)

        # Check for the debug log message
        # The log message includes the hex string WITHOUT "0x" prefix for each byte, and is lower case.
        expected_log_payload = mfg_data_hex # The mfg.hex() produces lowercase without 0x
        self.assertTrue(any(f"UNI-T raw mfg data: {expected_log_payload}" in msg for msg in log_watcher.output),
                        f"Expected log message not found in {log_watcher.output}")

    def test_uni_t_invalid_data_short(self):
        parser_self = BleParser(report_unknown=False, discovery=True, filter_duplicates=False)
        parser_self.rssi = -70
        # mfg[0] = 0x12 (18), so total length 19. mfg goes from index 0 to 18.
        # String slice mfg[9:18] is mfg[9]...mfg[17] (9 bytes) - this is fine.
        # Temp slice mfg[18:20] needs mfg[18] and mfg[19]. mfg[19] is out of bounds.
        mfg_bytes = bytes.fromhex("12ffaabb" + "30"*15) # 15 bytes of '0x30' to make total payload 15+3 = 18 bytes for mfg[1:]
        mac_bytes = bytes.fromhex("112233445566")
        data = parse_uni_t(parser_self, mfg_bytes, mac_bytes)
        self.assertIsNone(data)

    def test_uni_t_string_decode_error_or_format(self):
        # Test if string parsing fails gracefully due to bad format (no M/S)
        # Parser now uses mfg[9:18] for the string.
        parser_self = BleParser(report_unknown=False, discovery=True, filter_duplicates=False)
        parser_self.rssi = -70
        # Valid length (mfg[0]=0x14 -> 21 bytes total).
        # Original mfg_data_hex = "14ffaabb002020322e373520202020201b01000000"
        # mfg[9:18] from this is "322e37352020202020" -> "2.75      "
        # This doesn't contain "M/S", so txt.split("M/S") will fail.
        mfg_data_hex = "14ffaabb002020322e373520202020201b01000000" 
        mfg_bytes = bytes.fromhex(mfg_data_hex)
        mac_bytes = bytes.fromhex("112233445566")
        data = parse_uni_t(parser_self, mfg_bytes, mac_bytes)
        self.assertIsNone(data)

    def test_uni_t_temp_parse_error(self):
        # Test if temperature parsing fails due to insufficient bytes after string
        # String mfg[9:18] uses up to index 17. Temperature needs mfg[18] and mfg[19].
        # If mfg[0] implies total length is too short for mfg[19] (i.e. len(mfg) < 20)
        parser_self = BleParser(report_unknown=False, discovery=True, filter_duplicates=False)
        parser_self.rssi = -70

        # mfg_bytes_actually_short is 17 bytes long (indices 0-16).
        # Accessing mfg[18:20] will cause an IndexError because mfg[18] is out of bounds.
        mfg_bytes_actually_short = bytes.fromhex("AABBCCDDEEFF00112233445566778899AA") # 17 bytes long
        mac_bytes = bytes.fromhex("112233445566")
        data = parse_uni_t(parser_self, mfg_bytes_actually_short, mac_bytes)
        self.assertIsNone(data)

if __name__ == '__main__':
    unittest.main()
