# coding: utf-8
'''
It works by using Mitsubishi PLC FX5 SLMP protocol.

Recommended manuals
 1.全般 in FX5 User's manual(SLMP)
 2.エラーコード in FX5 User's manual(Ethernet connection)
 3.デバイスコード一覧 in FX5 User's manual(MC protocol)
'''
import socket
import struct
from threading import RLock

'''
Example
    fx5 = FX5.get_connection('192.168.1.10:2555')
    fx5.write('D500', 30)
    print(fx5.read('D500')) # -> 30
    fx5.write('M1600', 1)
    print(fx5.read('M1600')) # -> 1
'''
class FX5:

    __connections = {}

    #If you use same a host, you should use same an instance.
    @classmethod
    def get_connection(cls, host):
        if host not in cls.__connections:
            cls.__connections[host] = FX5(host)
        return cls.__connections[host]
    
    @classmethod
    def close_all(cls):
        '''Close all connections'''
        for con_host in cls.__connections:
            con = cls.get_connection(con_host)
            con.close()

    __ip = None
    __port = None
    __client = None
    __lock = RLock()
    __isopen = False

    '''
    Args:
        host (str): IP address:Port number
    '''
    def __init__(self, host):
        self.__ip, self.__port = host.split(':')
    
    def __str__(self):
        return self.__ip + ":" + self.__port + " " + ("Open" if self.__isopen else "Close")
    
    def __open(self):
        '''Connect to NC'''
        #未接続なら接続
        if not self.__isopen:
            self.__client = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # IPv4,TCP
            self.__client.settimeout(2) # 秒
            self.__client.connect((self.__ip, int(self.__port))) # IPとPORTを指定してバインドします
            self.__isopen = True

    def __send(self, data):
        '''Send instruction words to PLC on TCP socket connection.

        When some errors occur, it will throw error codes with hexadecimal.

        Args:
            data (list): data sentence
        
        Return:
            list: responsed data with array (exp: [10, 20, ....])
        '''
        with self.__lock:
            try:
                self.__open()
                self.__client.sendall(data)
                result = self.__client.recv(128)

                # check errors
                if len(result) < 11:
                    # Length of responsed data is required over 11 bytes
                    # Note: One port uses only one device in FX5.
                    raise Exception('Connection error. It already may connect other device.' + str(len(result)))
            except Exception as e:
                self.close()
                raise e

            # Sample
            # 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19
            # D0-00-00-FF-FF-03-00-03-00-00-00-10-00-00-00-00-00-00-00-00
            if format(result[9], '#04x') != '0x00' and format(result[10], '#04x') != '0x00':
                # Sum 2 bytes(the second byte must be 8-bit shift) to get unsigned 16-bit integer
                res_u16bit = self.to_int16_unsigned(result[10], result[9])
                if res_u16bit in self.__error:
                    errmsg = self.__error[res_u16bit]
                else:
                    errmsg = "unknown error"
                raise Exception('Error code: ' + str(res_u16bit) + " " + errmsg)

            # If there are no erros, it returns responsed data
            length = self.to_int16_signed(result[8], result[7]) - 2 # exclude end code(2byte)
            re = []
            for i in range(length):
                re.append(result[11 + i])
            return re

    def close(self):
        try:
            self.__isopen = False
            self.__client.close()
        except:
            pass

    def is_open(self):
        '''After calling '__open()' method, you can check if connection is open.
        
        Return:
            bool: True of False
        '''
        with self.__lock:
            try:
                self.__open()
            except:
                pass
            return self.__isopen

    def exec_cmd(self, cmd):
        '''Exceute commands with values.

        You must use below rules.
        ・Put string '=' between device name and value.
        ・Put string ',' to separate devices.

        exp)
        D150=31,D200=5,D300=2,D160=1,D210=1,D310=1,M1501=1

        Args:
            cmd (str): device names and values
        '''
        for dev_value in cmd.split(','):
            dev, value = dev_value.split('=')
            self.write(dev, value)

    def read(self, devno, as_ascii=False):
        dev_type = devno[0]
        dev_no = int(devno[1:])
        if dev_type == 'M':
            return self.__read_m(dev_no)
        elif dev_type == 'D':
            return self.__read_d(dev_no, as_ascii)
        raise Exception("Unsupported device type")
    
    def write(self, devno, value, as_ascii=False):
        dev_type = devno[0]
        dev_no = int(devno[1:])
        if dev_type == 'M':
            return self.__write_m(dev_no, int(value))
        elif dev_type == 'D':
            return self.__write_d(dev_no, value, as_ascii)
        raise Exception("Unsupported device type")

    def __read_m(self, devno):
        '''Read device 'M'

        Args:
            devno (int): device number
        
        Return:
            bool: return boolean from a bit(1=True, 0=False).
        '''
        msg = [
            0x50, 0x00, # sub header（fixed FX5U）
            0x00, # required network number（fixed FX5U）
            0xFF, # required area code（fixed FX5U）
            0xFF, 0x03, # required unit I/O number（fixed FX5U）
            0x00, # required multi drop area code（fixed FX5U）
            0x0C, 0x00, # required data length (byte size after reserved code)
            0x00, 0x00, # reserved code
            0x01, 0x04, # read command with bulk
            0x01, 0x00, # sub command（bit unit）
            devno & 0xff, # first device number（from lower byte）
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0x90, # device code 90=M
            0x01, 0x00 # device point（fixed 1）
        ]
        pack_msg = struct.pack('21B', *msg)
        re = self.__send(pack_msg)
        return format(re[0], '#04x') == '0x10'

    def __write_m(self, devno, on):
        '''Write device 'M'.

        Args:
            devno (int): device number
            on (bool): return boolean from a bit(1=True, 0=False).
        '''
        msg = [
            0x50, 0x00,
            0x00,
            0xFF,
            0xFF, 0x03,
            0x00,
            0x0D, 0x00,
            0x00, 0x00,
            0x01, 0x14, # write command with bulk
            0x01, 0x00,
            devno & 0xff,
            devno>>8 & 0xff,
            devno>>16 & 0xff,0x90, # device code 90=M
            0x01, 0x00,
            0x10 if on == True else 0x00 # write data
        ]
        pack_msg = struct.pack('22B', *msg)
        self.__send(pack_msg)
        return

    def __read_d(self, devno, as_ascii=False):
        '''Read device 'D'

        Args:
            devno (int): device number
            as_ascii (bool): you can use this argument when value is ASCII code.
        
        Return:
            int or str: If you use as_ascii, it returns string.
        '''
        msg = [
            0x50, 0x00,
            0x00,
            0xFF,
            0xFF, 0x03,
            0x00,
            0x0C, 0x00,
            0x00, 0x00,
            0x01, 0x04,
            0x00, 0x00,
            devno & 0xff,
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0xA8, # device code A8=D
            0x01, 0x00
        ]
        pack_msg = struct.pack('21B', *msg)
        re = self.__send(pack_msg)
        if as_ascii:
            return self.to_string(re[0], re[1])
        else:
            return self.to_int16_signed(re[1], re[0])

    def __write_d(self, devno, data, as_ascii=False):
        '''Write device 'D'.

        Args:
            devno (int): device number
            data (int or str): value
            as_ascii (bool): you can use this argument when value is ASCII code.
        '''
        if as_ascii:
            if len(data) > 2:
                raise Exception("you can write only 2 words")
            tuple_data = self.to_ascii(str(data)) # convert to (low, high)
        else:
            tuple_data = self.to_2bite_signed(int(data)) # convert to (low, high)
        msg = [
            0x50, 0x00,
            0x00,
            0xFF,
            0xFF, 0x03,
            0x00,
            0x0E, 0x00,
            0x00, 0x00,
            0x01, 0x14,
            0x00, 0x00,
            devno & 0xff,
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0xA8, # device code A8=D
            0x01, 0x00,
            tuple_data[0], tuple_data[1] # low, high
        ]
        pack_msg = struct.pack('23B', *msg)
        self.__send(pack_msg)
        return
    
    def to_int16_signed(self, upper, lower):
        '''convert 2-byte(8bit/hex) to unsigned 16-bit
        
        Args:
            upper (int): upper byte
            lower (int): lower byte
        
        Return:
            int：signed 16-bit
        '''
        num = (upper<<8) + lower
        return -(num & 0b1000000000000000) | (num & 0b0111111111111111)

    def to_int16_unsigned(self, upper, lower):
        '''convert 2-byte(8bit 16hex) to unsigned 16-bit
        
        Args:
            upper (int): upper byte
            lower (int): lower byte
        
        Return:
            int：signed 16-bit
        '''
        return (upper<<8) + lower

    def to_string(self, upper, lower):
        '''convert 2-byte(8bit/hex) to two strings
        
        Args:
            upper (int): upper byte
            lower (int): lower byte
        
        Return:
            string：two strings
        '''
        return (chr(upper) if upper != 0 else '') + (chr(lower) if lower != 0 else '')
    
    def to_2bite_signed(self, num):
        '''convert integer to signed 2-byte

        Args:
            num (int): target number
        
        Return:
            tuple(int,int)：signed 2-byte（low, high)
        '''
        import struct
        pack = struct.pack('H', num) # H = unsigned short/integer/size:2
        return struct.unpack('BB', pack) # B = unsigned char/integer/size:1

    def to_ascii(self, str_data):
        '''convert strings(from 0 length to 2 length) to integer（tuple）.

        Args:
            str_data (str): strings

        Return:
            tuple(int,int)：integer (lower, upper)
        '''
        if len(str_data) == 2:
            lower = ord(str_data[0])
            upper = ord(str_data[1])
        elif len(str_data) == 1:
            lower = ord(str_data[0])
            upper = 0
        else:
            lower = 0
            upper = 0
        return (lower, upper)

    # quote FX5 manual in Mitsubishi site
    # (I translated into English by using Google translation
    #  So don't ask me detailed meaning of errors..., sorry.)
    __error = {
        0x1920: 'The value of the IP address setting (SD8492 to SD8497) is out of the setting range. ',
        0x1921: 'The write request and the clear request (SM8492, SM8495) were turned off and on at the same time. ',
        0x112E: 'Connection not established during open processing. ',
        0x1134: 'A TCP ULP timeout error occurred during TCP / IP communication (ACK was not returned from the partner device). ',
        0x2160: 'A duplicate IP address has been detected. ',
        0x2250: 'The protocol setting data stored in the CPU unit is not a usable unit. ',
        0xC012: 'Open processing with the partner device failed. (For TCP / IP) ',
        0xC013: 'The open processing with the partner device failed. (For UDP / IP) ',
        0xC015: 'There is an error in the setting value of the IP address of the external device during open processing, or the setting of the IP address of the external device in the dedicated command. ',
        0xC018: 'The setting of the IP address of the partner device is incorrect. ',
        0xC020: 'The transmission / reception data length exceeds the allowable range. ',
        0xC024: 'Communication using communication protocol was performed in connection other than communication protocol. ',
        0xC025: 'The content of the control data is incorrect or the open setting parameter has not been set, but the open setting parameter was specified. ',
        0xC027: 'Message transmission of socket communication failed. ',
        0xC029: 'The content of the control data is incorrect, or the open setting parameter was specified as open without setting. ',
        0xC035: 'The existence of the partner device could not be confirmed within the response monitoring timer value. ',
        0xC0B6: 'The channel specified by the dedicated instruction is out of range. ',
        0xC0DE: 'Failed to receive message for socket communication. ',
        0xC1A2: 'Response to request could not be received. ',
        0xC1AC: 'The number of retransmissions is incorrect. ',
        0xC1AD: 'The data length is incorrectly specified. ',
        0xC1AF: 'The port number is incorrectly specified. ',
        0xC1B0: 'The specified connection has already been opened. ',
        0xC1B1: 'The specified connection has not completed open processing. ',
        0xC1B3: 'Another transmission / reception command is being executed on the specified channel. ',
        0xC1B4: 'The arrival time specification is incorrect. ',
        0xC1BA: 'The dedicated instruction was executed in the initial uncompleted state. ',
        0xC1C6: 'There is an error in the setting of the execution type of the dedicated instruction and the completion type when an error occurs. ',
        0xC1CC: 'Response with a data length exceeding the allowable range in SLMPSND was received, or the request data was specified incorrectly. ',
        0xC1CD: 'Failed to send message of SLMPSND command. ',
        0xC1D0: 'The request destination module I / O number of the dedicated instruction is incorrect. ',
        0xC1D3: 'A dedicated command not supported by the connection communication method was executed. ',
        0xC400: 'The SP.ECPRTCL instruction was executed when communication protocol preparation was not completed (SD10692 = 0). ',
        0xC401: 'Specified a protocol number that is not registered in the CPU unit with the control data of the SP.ECPRTCL instruction, or executed the SP.ECPRTCL instruction without writing the protocol setting data. ',
        0xC404: 'The SP.ECPRTCL instruction was abnormally completed while accepting a cancel request during protocol execution. ',
        0xC405: 'In the control data of the SP.ECPRTCL instruction, the set value of the protocol number is out of range. ',
        0xC410: 'Reception waiting time has timed out. ',
        0xC411: 'The received data has exceeded 2046 bytes. ',
        0xC417: 'The data length of received data or the number of data is out of range. ',
        0xC431: 'Connection closed during execution of the SP.ECPRTCL instruction. ',
        0xCEE0: 'Detected from another peripheral device or executed another iQSS function during automatic detection of connected device. ',
        0xCEE1: 'An abnormal frame was received. ',
        0xCEE2: 'An abnormal frame was received. ',
        0xCF10: 'An abnormal frame was received. ',
        0xCF20: 'The communication setting value is out of range, or a communication setting item that cannot be set for the target device has been set, or an item that must be set for the target device has not been set. ',
        0xCF30: 'Parameter not supported by target device was specified. ',
        0xCF31: 'An abnormal frame was received. ',
        0xCF70: 'An error has occurred in the Ethernet communication path. ',
        0xCF71: 'A timeout error has occurred. ',
        0xC050: 'When communication data code is set to ASCII, ASCII code data that cannot be converted to binary was received. ',
        0xC051: 'The maximum number of bit devices that can be read / written at once at one time is out of the allowable range. ',
        0xC052: 'The maximum number of word devices that can be read / written at once at one time is out of the allowable range. ',
        0xC053: 'The maximum number of bit devices that can be randomly read and written at one time is out of the allowable range. ',
        0xC054: 'The maximum number of word devices that can be read / written at random at one time is out of the allowable range. ',
        0xC056: 'Write and read request exceeding the maximum address. ',
        0xC058: 'The required data length after ASCII-binary conversion does not match the number of data in the character part (part of text). ',
        0xC059: 'The command or subcommand specification is incorrect. Commands and subcommands that cannot be used in the CPU unit. ',
        0xC05B: 'The CPU unit cannot write to or read from the specified device. ',
        0xC05C: 'The request content is incorrect. (Such as bit-wise writing and reading for word devices) ',
        0xC05F: 'The request cannot be executed for the target CPU module',
        0xC060: 'The request content is incorrect. (Such as an incorrect data specification for a bit device) ',
        0xC061: 'The requested data length does not match the number of data in the character part (part of text). ',
        0xC06F: 'ASCII request message was received when the communication data code was set to "binary." (For this error code, only the error history is registered and no abnormal response is returned.) ',
        0xC0D8: 'The specified number of blocks is out of range',
        0xC200: 'The remote password is incorrect',
        0xC201: 'The port used for communication is locked with the remote password',
        0xC204: 'Different from the partner device that requested unlock processing of the remote password. ',
        0xC810: 'The remote password is incorrect. (Authentication failed 9 times or less) ',
        0xC815: 'The remote password is incorrect. (Authentication failed 10 times) ',
        0xC816: 'Remote password authentication lockout in progress. '
        #0x4000H～4FFF : 'CPU unit finds errors.（exclude connection SLMP'
        }