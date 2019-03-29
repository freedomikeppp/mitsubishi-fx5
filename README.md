# mitsubishi-fx5
三菱FX5シーケンサを操作するPythonのサンプルです。

主にDデバイスとMデバイスへの値の読み込みと書き込みが行えます。

自身の環境で実装する際のヒントとしてお使い下さい。

# 使い方

```
# Open connection
fx5 = FX5.get_connection('192.168.1.10:2555')

# Dデバイスへの操作
fx5.write('D500', 30)
print(fx5.read('D500')) # -> 30

# Mデバイスへの操作
fx5.write('M1600', 1)
print(fx5.read('M1600')) # -> 1

# 複数デバイスへの値の書き込み
fx5.exec_cmd('D150=31,D200=5,D300=2')

# Close connection
fx5.close()
```
