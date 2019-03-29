# coding: utf-8
'''
三菱電機PLC FX5 SLMPプロトコルにて通信。

必読マニュアル
 1.全般 FX5ユーザーズマニュアル(SLMP編)
 2.エラーコード  FX5ユーザーズマニュアル(Ethernet通信編)
 3.デバイスコード一覧  FX5ユーザーズマニュアル(MCプロトコル編)
'''
import socket
import struct
from threading import RLock

'''
使い方

    fx5 = FX5.get_connection('192.168.1.10:2555')
    fx5.write('D500', 30)
    print(fx5.read('D500')) # -> 30
    fx5.write('M1600', 1)
    print(fx5.read('M1600')) # -> 1
'''
class FX5:

    __connections = {}

    #同一ホストの接続は同じインスタンスを使う
    @classmethod
    def get_connection(cls, host):
        if host not in cls.__connections:
            cls.__connections[host] = FX5(host)
        return cls.__connections[host]
    
    @classmethod
    def close_all(cls):
        '''コネクションを全て閉じる'''
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
        host: IPアドレス:ポート番号
    '''
    def __init__(self, host):
        self.__ip, self.__port = host.split(':')
    
    def __str__(self):
        return self.__ip + ":" + self.__port + " " + ("Open" if self.__isopen else "Close")
    
    def __open(self):
        '''NCに接続します。'''
        #未接続なら接続
        if not self.__isopen:
            self.__client = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # IPv4,TCP
            self.__client.settimeout(2) # 秒
            self.__client.connect((self.__ip, int(self.__port))) # IPとPORTを指定してバインドします
            self.__isopen = True

    def __send(self, data):
        '''PLCにTCPソケット通信で命令伝文を送る。

        エラーの場合は　C05C　など16進数でエラーコードをThrowします。
        エラーコードは FX5ユーザーズマニュアル(Ethernet通信編)を参照の事。

        Args:
            data (list): 伝文
        
        Return:
            list: 応答データを配列で返す (exp: [10, 20, ....])
        '''
        with self.__lock:
            try:
                self.__open()
                self.__client.sendall(data)
                result = self.__client.recv(128) # 今回の通信なら20でも十分

                # 通信Errorチェック
                if len(result) < 11:
                    # 応答伝文長さは11byte以上になるので、満たない場合は通信エラー
                    # FX5は同じポートに同時接続は1機器だけなので、他がつないでいると応答を返さない
                    # 以降読み書きできないのでいったん閉じておく
                    raise Exception('通信エラー、他端末と通信中の可能性' + str(len(result)))
            except Exception as e:
                self.close()
                raise e

            # Sample
            # 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19
            # D0-00-00-FF-FF-03-00-03-00-00-00-10-00-00-00-00-00-00-00-00
            if format(result[9], '#04x') != '0x00' and format(result[10], '#04x') != '0x00':
                # 連続2バイト(2バイト目は8bit左シフト)を積算し、16ビット符号なし整数
                res_u16bit = self.to_int16_unsigned(result[10], result[9])
                if res_u16bit in self.__error:
                    errmsg = self.__error[res_u16bit]
                else:
                    errmsg = "不明なエラーです"
                raise Exception('Error code: ' + str(res_u16bit) + " " + errmsg)

            # エラーがなければ応答データ部分だけ返す
            length = self.to_int16_signed(result[8], result[7]) - 2 # 応答データ長計算 終了コードの2バイトは除く
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
        '''__open()処理後、接続が開いているか確認する。
        
        Return:
            bool: 接続が開いているならTrue
        '''
        with self.__lock:
            try:
                self.__open()
            except:
                pass
            return self.__isopen

    def exec_cmd(self, cmd):
        '''指定されたデバイスと値の文字列を実行する。

        文字列は必ず下記のルールに従う。
        ・デバイス名と値は、'='で繋ぐ。
        ・デバイスごとに、','で区切る。

        exp)
        D150=31,D200=5,D300=2,D160=1,D210=1,D310=1,M1501=1

        Args:
            cmd (str): デバイスと値の文字列
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
        raise Exception("未対応デバイスタイプです")
    
    def write(self, devno, value, as_ascii=False):
        dev_type = devno[0]
        dev_no = int(devno[1:])
        if dev_type == 'M':
            return self.__write_m(dev_no, int(value))
        elif dev_type == 'D':
            return self.__write_d(dev_no, value, as_ascii)
        raise Exception("未対応デバイスタイプです")

    def __read_m(self, devno):
        '''デバイス M ビット読み込み。

        Args:
            devno (int): デバイス番号
        
        Return:
            bool: ビット（1=True, 0=False） から真偽値を返す。
        '''
        msg = [
            0x50, 0x00, # サブヘッダ（FX5U固定）
            0x00, # 要求先ネットワーク番号（FX5U固定）
            0xFF, # 要求先局番（FX5U固定）
            0xFF, 0x03, # 要求先ユニットI/O番号（FX5U固定）
            0x00, # 要求先マルチドロップ局番（FX5U固定）
            0x0C, 0x00, # 要求データ長(リザーブ以降のバイト長)
            0x00, 0x00, # リザーブ
            0x01, 0x04, # 一括読み込み
            0x01, 0x00, # サブコマンド（ビット単位）
            devno & 0xff, # 先頭デバイス番号（intを下位バイトから渡す）
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0x90, # デバイスコード 90=M
            0x01, 0x00 # デバイス点数（1固定とする）
        ]
        pack_msg = struct.pack('21B', *msg)
        re = self.__send(pack_msg)
        return format(re[0], '#04x') == '0x10'

    def __write_m(self, devno, on):
        '''デバイス M ビット書き込み。

        Args:
            devno (int): デバイス番号
            on (bool): ビット（1=True, 0=False） 
        '''
        msg = [
            0x50, 0x00, # サブヘッダ（FX5U固定）
            0x00, # 要求先ネットワーク番号（FX5U固定）
            0xFF, # 要求先局番（FX5U固定）
            0xFF, 0x03, # 要求先ユニットI/O番号（FX5U固定）
            0x00, # 要求先マルチドロップ局番（FX5U固定）
            0x0D, 0x00, # 要求データ長(リザーブ以降のバイト長)
            0x00, 0x00, # リザーブ
            0x01, 0x14, # 一括書き込みコマンド
            0x01, 0x00, # サブコマンド（ビット単位）
            devno & 0xff, # 先頭デバイス番号（intを下位バイトから渡す）
            devno>>8 & 0xff,
            devno>>16 & 0xff,0x90, # デバイスコード 90=M
            0x01, 0x00, # デバイス点数（1固定とする）
            0x10 if on == True else 0x00 # 点数分の書き込みデータ（1バイトで渡すので）
        ]
        pack_msg = struct.pack('22B', *msg)
        self.__send(pack_msg)
        return

    def __read_d(self, devno, as_ascii=False):
        '''デバイス D からワード読み込み。

        Args:
            devno (int): デバイス番号
            as_ascii (bool): Dデバイスの値がASCIIで格納されている場合に指定する。
        
        Return:
            int or str: as_ascii指定なら文字列、指定無しなら数値を返す。
        '''
        msg = [
            0x50, 0x00, # サブヘッダ（FX5U固定）
            0x00, # 要求先ネットワーク番号（FX5U固定）
            0xFF, # 要求先局番（FX5U固定）
            0xFF, 0x03, # 要求先ユニットI/O番号（FX5U固定）
            0x00, # 要求先マルチドロップ局番（FX5U固定）
            0x0C, 0x00, # 要求データ長(リザーブ以降のバイト長)
            0x00, 0x00, # リザーブ
            0x01, 0x04, # 一括読み込み
            0x00, 0x00, # サブコマンド（ワード単位）
            devno & 0xff, # 先頭デバイス番号（intを下位バイトから渡す）
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0xA8, # デバイスコード A8=D
            0x01, 0x00 # デバイス点数（1固定とする）
        ]
        pack_msg = struct.pack('21B', *msg)
        re = self.__send(pack_msg)
        if as_ascii:
            return self.to_string(re[0], re[1])
        else:
            return self.to_int16_signed(re[1], re[0])

    def __write_d(self, devno, data, as_ascii=False):
        '''デバイス D ビット書き込み。

        Args:
            devno (int): デバイス番号
            data (int or str): 書き込む値
            as_ascii (bool): Dデバイスの値がASCIIで格納されている場合に指定する。
        '''
        if as_ascii:
            if len(data) > 2:
                raise Exception("DデバイスにASCIIで書き込める文字列は、2文字までです。")
            tuple_data = self.to_ascii(str(data)) # (low, high)に変換
        else:
            tuple_data = self.to_2bite_signed(int(data)) # (low, high)に変換
        msg = [
            0x50, 0x00, # サブヘッダ（FX5U固定）
            0x00, # 要求先ネットワーク番号（FX5U固定）
            0xFF, # 要求先局番（FX5U固定）
            0xFF, 0x03, # 要求先ユニットI/O番号（FX5U固定）
            0x00, # 要求先マルチドロップ局番（FX5U固定）
            0x0E, 0x00, # 要求データ長(リザーブ以降のバイト長)
            0x00, 0x00, # リザーブ
            0x01, 0x14, # 一括書き込み
            0x00, 0x00, # サブコマンド（ワード単位）
            devno & 0xff, # 先頭デバイス番号（intを下位バイトから渡す）
            devno>>8 & 0xff,
            devno>>16 & 0xff,
            0xA8, # デバイスコード A8=D
            0x01, 0x00, # デバイス点数（1固定とする）
            tuple_data[0], tuple_data[1] # low, high
        ]
        pack_msg = struct.pack('23B', *msg)
        self.__send(pack_msg)
        return
    
    def to_int16_signed(self, upper, lower):
        '''連続2バイトの8ビット16進数を、16ビット符号付きに変換する。

        主に、三菱シーケンサFX5の応答データを変換する際に使用する。
        上位8ビットを左シフトして、下位8ビットと足し合わせたのち、符号付き変換の処理をする。
        
        Args:
            upper (int): 上位バイト
            lower (int): 下位バイト
        
        Return:
            int：16ビット符号付き
        '''
        num = (upper<<8) + lower
        return -(num & 0b1000000000000000) | (num & 0b0111111111111111)

    def to_int16_unsigned(self, upper, lower):
        '''連続2バイトの8ビット16進数を、16ビット符号無しに変換する。

        主に、三菱シーケンサFX5の応答データのエラーコード変換する際に使用する。
        上位8ビットを左シフトして、下位8ビットと足し合わせた、符号無し変換の処理をする。
        
        Args:
            upper (int): 上位バイト
            lower (int): 下位バイト
        
        Return:
            int：16ビット符号付き
        '''
        return (upper<<8) + lower

    def to_string(self, upper, lower):
        '''連続2バイトの8ビット16進数を、ASCIIコードとして解釈し、2つの文字列に変換する。

        主に、三菱シーケンサFX5の応答データを変換する際に使用する。
        Dデバイスに格納された、2文字のASCIIコードを、文字列に変換する。
        
        Args:
            upper (int): 上位バイト
            lower (int): 下位バイト
        
        Return:
            string：2つの文字列
        '''
        # upperまたはlowerが0の場合は、ASCIIコードではnullのため空文字にする
        return (chr(upper) if upper != 0 else '') + (chr(lower) if lower != 0 else '')
    
    def to_2bite_signed(self, num):
        '''整数を、符号付き2バイト（tuple）に変換する。

        三菱シーケンサFX5のデバイスD書き込み時に使用する。
        シーケンサへは、送りたい整数データを符号付き2バイトに
        変換して送る必要がある。

        変換に使用する、structモジュールについては公式ドキュメント参照。
        https://docs.python.jp/3/library/struct.html

        Args:
            num (int): 変換対象の整数。
        
        Return:
            tuple(int,int)：符号付き2バイト（low, high)
        '''
        import struct
        pack = struct.pack('H', num) # H = unsigned short/整数/size:2
        return struct.unpack('BB', pack) # B = unsigned char/整数/size:1

    def to_ascii(self, str_data):
        '''文字列(0文字以上, 2文字以下)を、ASCIIコードとして解釈し、数値（tuple）に変換する。

        三菱シーケンサFX5のデバイスD書き込み時に使用する。
        シーケンサへは、送りたい整数データを符号付き2バイトに
        変換して送る必要がある。
        
        Args:
            str_data (str): 変換対象の文字列（0文字以上, 2文字以下）

        Return:
            tuple(int,int)：数値、但し順番は（lower, upper)
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

    #FX5マニュアルよりのエラーコード表（16ビット符号なし整数）
    __error = {
        0x1920 : 'IPアドレス設定など（SD8492～SD8497）の値が設定範囲外です。',
        0x1921 : '書込み要求とクリア要求（SM8492、SM8495）が同時にOFF→ONされました。',
        0x112E : 'オープン処理で、コネクションが確立されませんでした。',
        0x1134 : 'TCP/IPの交信で、TCP ULPタイムアウトエラーが発生（相手機器からACKが返されない）しました。',
        0x2160 : 'IPアドレスの重複を検出しました。',
        0x2250 : 'CPUユニットに格納されているプロトコル設定データが、使用できるユニットではありません。',
        0xC012 : '相手機器とのオープン処理に失敗しました。（TCP/IPの場合）',
        0xC013 : '相手機器とのオープン処理に失敗しました。（UDP/IPの場合）',
        0xC015 : 'オープン処理時の、相手機器のIPアドレスの設定値に誤り、または、 専用命令の相手機器IPアドレスの設定に誤りがあります。',
        0xC018 : '相手機器IPアドレスの設定に誤りがあります。',
        0xC020 : '送受信データ長が許容範囲を超えています。',
        0xC024 : '交信手段が通信プロトコル以外のコネクションにて、通信プロトコルによる交信を実施しました。',
        0xC025 : 'コントロールデータの内容に誤りがある、または、オープン設定パラメータが未設定なのに、オープン設定パラメータでのオープンを指定されました。',
        0xC027 : 'ソケット通信の伝文送信に失敗しました。',
        0xC029 : 'コントロールデータの内容に誤り、または、 オープン設定パラメータが未設定でオープン指定されました。',
        0xC035 : 'レスポンス監視タイマ値以内に、相手機器の生存確認ができませんでした。',
        0xC0B6 : '専用命令で指定されたチャンネルが範囲外です。',
        0xC0DE : 'ソケット通信の伝文受信に失敗しました。',
        0xC1A2 : '要求に対する応答を受信できませんでした。',
        0xC1AC : '再送回数の指定に誤りがあります。',
        0xC1AD : 'データ長の指定に誤りがあります。',
        0xC1AF : 'ポート番号の指定に誤りがあります。',
        0xC1B0 : '指定されたコネクションは既にオープン処理が完了してます。',
        0xC1B1 : '指定されたコネクションはオープン処理が完了してません。',
        0xC1B3 : '指定されたチャンネルは他の送受信命令が実行中です。',
        0xC1B4 : '到達時間の指定に誤りがあります。',
        0xC1BA : 'イニシャル未完了状態で専用命令が実行されました。',
        0xC1C6 : '専用命令の実行・異常時完了タイプの設定に誤りがあります。',
        0xC1CC : 'SLMPSNDで許容範囲を超えるデータ長の応答を受信、または、要求データの指定に誤りがあります。',
        0xC1CD : 'SLMPSND命令の伝文送信に失敗しました。',
        0xC1D0 : '専用命令の要求先ユニットI/O番号に誤りがあります。',
        0xC1D3 : 'コネクションの交信手段に対応していない専用命令が実行されました。',
        0xC400 : '通信プロトコル準備未完了時（SD10692=0）にSP.ECPRTCL命令を実行しました。',
        0xC401 : 'CPUユニットに登録されていないプロトコル番号を、SP.ECPRTCL命令のコントロールデータで指定し、または、プロトコル設定データを書き込んでいない状態でSP.ECPRTCL命令を実行しました。',
        0xC404 : 'プロトコル実行中にキャンセル要求を受け付けて、SP.ECPRTCL命令を異常完了しました。',
        0xC405 : 'SP.ECPRTCL命令のコントロールデータにおいて、プロトコル番号の設定値が範囲外です。',
        0xC410 : '受信待ち時間がタイムアップしました。',
        0xC411 : '受信したデータが2046バイトを超えました。',
        0xC417 : '受信したデータのデータ長、またはデータ数が範囲外です。',
        0xC431 : 'SP.ECPRTCL命令実行中にコネクションクローズ発生しました。',
        0xCEE0 : '接続機器の自動検出中に、他の周辺機器から検出、または他のiQSS機能を実行しました。',
        0xCEE1 : '異常なフレームを受信しました。',
        0xCEE2 : '異常なフレームを受信しました。',
        0xCF10 : '異常なフレームを受信しました。',
        0xCF20 : '通信設定の設定値が範囲外、または、対象機器に設定できない通信設定項目を設定、または、対象機器で設定必須の項目が未設定です。',
        0xCF30 : '対象機器がサポートしていないパラメータを指定しました。',
        0xCF31 : '異常なフレームを受信しました。',
        0xCF70 : 'Ethernetの通信経路で異常が発生しました。',
        0xCF71 : 'タイムアウトエラーが発生しました。',
        0xC050 : '交信データコードがASCIIに設定されている場合に、バイナリ変換できないASCIIコードのデータを受信しました。',
        0xC051 : '一度に一括読み書きできる最大ビットデバイス数が許容範囲外である。',
        0xC052 : '一度に一括読み書きできる最大ワードデバイス数が許容範囲外である。',
        0xC053 : '一度にランダム読み書きできる最大ビットデバイス数が許容範囲外である。',
        0xC054 : '一度にランダム読み書きできる最大ワードデバイス数が許容範囲外である。',
        0xC056 : '最大アドレスを超える書込みおよび読出し要求である。',
        0xC058 : 'ASCII－バイナリ変換後の要求データ長が、キャラクタ部（テキストの一部）のデータ数と合わない。',
        0xC059 : 'コマンド、サブコマンドの指定に誤りがある。CPUユニットでは使用不可のコマンド、サブコマンドである。',
        0xC05B : '指定デバイスに対してCPUユニットが書込みおよび読出しできない。',
        0xC05C : '要求内容に誤りがある。（ワードデバイスに対するビット単位の書込みおよび読出しなど）',
        0xC05F : '対象CPUユニットに対して実行できない要求である',
        0xC060 : '要求内容に誤りがある。（ビットデバイスに対するデータの指定に誤りがあるなど）',
        0xC061 : '要求データ長が、キャラクタ部（テキストの一部）のデータ数と合わない。',
        0xC06F : '交信データコードが”バイナリ”に設定されている場合に、ASCIIの要求伝文を受信した。（本エラーコードは、エラー履歴のみ登録され異常応答は返りません）',
        0xC0D8 : '指定したブロック数が範囲を超えています',
        0xC200 : 'リモートパスワードに誤りがある',
        0xC201 : '交信に使ったポートがリモートパスワードのロック状態である',
        0xC204 : 'リモートパスワードのアンロック処理を要求した相手機器と異なる。',
        0xC810 : 'リモートパスワードに誤りがある。（認証失敗回数9回以下）',
        0xC815 : 'リモートパスワードに誤りがある。（認証失敗回数10回）',
        0xC816 : 'リモートパスワード認証ロックアウト中である。'
        #0x4000H～4FFF : 'CPUユニットが検出したエラー。（SLMPによる通信機能以外で発生したエラー）',
        }