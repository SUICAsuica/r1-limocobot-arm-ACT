from pymycobot import MyCobot280
import time


mc = MyCobot280("/dev/ttyACM0", 115200)

print("mode:", mc.get_transponder_mode())
print("set mode:", mc.set_transponder_mode(1))
print("free:", mc.is_free_mode())
print("set free 0:", mc.set_free_mode(0))
print("error:", mc.get_error_information())

angles = mc.get_angles()
print("angles:", angles)

target = angles[:]
target[5] += 2
print("send:", mc.send_angles(target, 10))
time.sleep(3)
print("after:", mc.get_angles())
