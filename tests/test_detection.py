import unittest
from detection.os_detect import detect_os
from detection.hardware_detect import detect_hardware

class TestLUODetection(unittest.TestCase):
    def test_os_detect(self):
        info = detect_os()
        self.assertIn("kernel", info)

    def test_hardware_detect(self):
        hw = detect_hardware()
        self.assertIn("cpu", hw)
        self.assertIn("ram_gb", hw)

if __name__ == "__main__":
    unittest.main()
