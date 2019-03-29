# coding: utf-8
'''
本テストは三菱FX5シーケンサのテストスクリプトです。
'''
import os
import sys
import unittest

from fx5 import FX5


class TestFX5(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        '''テストクラスが初期化される際に一度だけ呼ばれる。'''
        print('----- TestFX5 start ------')
        cls.fx5 = FX5.get_connection("192.168.32.218:2556")

    @classmethod
    def tearDownClass(cls):
        '''テストクラスが解放される際に一度だけ呼ばれる。'''
        cls.fx5.close()
        print('----- TestFX5 end ------')

    def setUp(self):
        '''テストごとに開始前に必ず実行'''
        if not self.fx5.is_open():
            self.skipTest('指定されたIPに接続できません。電源が入っていない可能性があります。')

    def test_to_int16_signed(self):
        '''連続2バイトの8ビット16進数を、16ビット符号付きに変換するテスト。'''
        # 0x000F = 15
        self.assertEqual(self.fx5.to_int16_signed(0x00, 0x0F), 15)
        # 0x00FF = 255
        self.assertEqual(self.fx5.to_int16_signed(0x00, 0xFF), 255)
        # 0x0FFF = 4095
        self.assertEqual(self.fx5.to_int16_signed(0x0F, 0xFF), 4095)
        # 0xFFFF = -1
        self.assertEqual(self.fx5.to_int16_signed(0xFF, 0xFF), -1)
        # 0xFF00 = -256
        self.assertEqual(self.fx5.to_int16_signed(0xFF, 0x00), -256)
        # 0xF000 = -4096
        self.assertEqual(self.fx5.to_int16_signed(0xF0, 0x00), -4096)

    def test_to_int16_unsigned(self):
        '''連続2バイトの8ビット16進数を、16ビット符号無しに変換するテスト。'''
        # 0x000F = 15
        self.assertEqual(self.fx5.to_int16_unsigned(0x00, 0x0F), 15)
        # 0x00FF = 255
        self.assertEqual(self.fx5.to_int16_unsigned(0x00, 0xFF), 255)
        # 0x0FFF = 4095
        self.assertEqual(self.fx5.to_int16_unsigned(0x0F, 0xFF), 4095)
        # 0xF0F0 = 61680
        self.assertEqual(self.fx5.to_int16_unsigned(0xF0, 0xF0), 61680)
        # 0xFF00 = 65280
        self.assertEqual(self.fx5.to_int16_unsigned(0xFF, 0x00), 65280)
        # 0xFFFF = 65535
        self.assertEqual(self.fx5.to_int16_unsigned(0xFF, 0xFF), 65535)

    def test_to_string(self):
        '''連続2バイトの8ビット16進数を、ASCIIコードとして解釈し、2つの文字列に変換するテスト。'''
        # 0x4142 = AB
        self.assertEqual(self.fx5.to_string(0x41, 0x42), 'AB')
        # 0x6162 = ab
        self.assertEqual(self.fx5.to_string(0x61, 0x62), 'ab')
        # 0x3031 = 01
        self.assertEqual(self.fx5.to_string(0x30, 0x31), '01')
        # 0x3839 = 89
        self.assertEqual(self.fx5.to_string(0x38, 0x39), '89')

    def test_to_2bite_signed(self):
        '''整数を、符号付き2バイト（tuple）に変換するテスト。'''
        self.assertEqual(self.fx5.to_2bite_signed(0), (0,0))
        self.assertEqual(self.fx5.to_2bite_signed(30), (30,0))
        self.assertEqual(self.fx5.to_2bite_signed(255), (255,0))
        self.assertEqual(self.fx5.to_2bite_signed(256), (0,1))
        self.assertEqual(self.fx5.to_2bite_signed(511), (255,1))
        self.assertEqual(self.fx5.to_2bite_signed(512), (0,2))
        self.assertEqual(self.fx5.to_2bite_signed(65280), (0, 255))
        self.assertEqual(self.fx5.to_2bite_signed(65535), (255, 255))

    def test_to_ascii(self):
        '''文字列(0文字以上, 2文字以下)を、ASCIIコードとして解釈し、数値（tuple）に変換するテスト。'''
        self.assertEqual(self.fx5.to_ascii('AB'), (65,66))
        self.assertEqual(self.fx5.to_ascii('ab'), (97,98))
        self.assertEqual(self.fx5.to_ascii('01'), (48,49))
        self.assertEqual(self.fx5.to_ascii('89'), (56,57))

    def test_m_dev_operation(self):
        '''Mデバイスの読み書きテスト。'''
        self.fx5.write('M1600', 0)
        self.assertEqual(self.fx5.read('M1600'), 0)
        self.fx5.write('M1600', 1)
        self.assertEqual(self.fx5.read('M1600'), 1)
    
    def test_d_dev_operation(self):
        '''Dデバイスの読み書きテスト。'''
        self.fx5.write('D500', 30)
        self.assertEqual(self.fx5.read('D500'), 30)
        self.fx5.write('D500', 3000)
        self.assertEqual(self.fx5.read('D500'), 3000)
        self.fx5.write('D500', 30000)
        self.assertEqual(self.fx5.read('D500'), 30000)

    def test_exec_cmd(self):
        '''デバイスの一括書き込みテスト。'''
        self.fx5.exec_cmd('M1600=1,D500=30')
        self.assertEqual(self.fx5.read('M1600'), 1)
        self.assertEqual(self.fx5.read('D500'), 30)

if __name__ == '__main__':
    unittest.main()
