import dbus
import sys
from time import sleep
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
from tornado.ioloop import PeriodicCallback
import tornado.web

PORT=8888

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global bt
        self.bt = bt
        self.callback = PeriodicCallback(self.check_status, 1000)
        self.callback.start()
        print "Opened Connection"

    def check_status(self):
        (btnA, btnB) = self.bt.getBtn()
        if btnA>0:
            self.write_message('Button A')
        if btnB>0:
            self.write_message('Button B')

    def send_echo(self, message):
        self.write_message(message)

    def on_message(self, message):
        self.bt.putLed(message)
        self.send_echo(message)
        pass

    def on_close(self):
        self.callback.stop()
        print "Closed Connection"


class IndexPageHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")
        print "Sent index.html"

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', IndexPageHandler),
            (r'/websocket', WebSocketHandler)
        ]
 
        settings = {
            'template_path': ''
        }
        tornado.web.Application.__init__(self, handlers, **settings)
 
class Bluetooth():
    def __init__(self, name='bogus'):
        self.setup(name)

    def setup(self, name):
        bus = dbus.SystemBus()
        bluez = bus.get_object('org.bluez','/')
        bluez_iface = dbus.Interface(bluez, 'org.freedesktop.DBus.ObjectManager')
        objects = bluez_iface.GetManagedObjects()

        for obj, ifaces in objects.items():
            if 'org.bluez.Device1' in ifaces.keys():
                if 'Name' in ifaces['org.bluez.Device1']:
                    if name in ifaces['org.bluez.Device1']['Name']:
                        print "Name match with", name
                        device_path = obj

        print device_path

        remote_device_obj = bus.get_object('org.bluez', device_path)
        self.remote_device_methods = dbus.Interface(remote_device_obj, 'org.bluez.Device1')
        self.remote_device_props = dbus.Interface(remote_device_obj, dbus.PROPERTIES_IFACE)

        self.remote_device_methods.Connect()

        while not self.remote_device_props.Get('org.bluez.Device1','ServicesResolved'):
            sleep(0.25)

        for obj, ifaces in objects.items():
            if 'org.bluez.GattCharacteristic1' in ifaces.keys():
                if obj.startswith(device_path):
                    if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dda90-251d-470a-a062-fa1922dfa9a8':
                        btn_a_path = obj
                    if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dda91-251d-470a-a062-fa1922dfa9a8':
                        btn_b_path = obj
                    if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95d93ee-251d-470a-a062-fa1922dfa9a8':
                        led_path = obj
                    if ifaces['org.bluez.GattCharacteristic1']['UUID'] == '6e400003-b5a3-f393-e0a9-e50e24dcca9e':
                        uart_path = obj

                
        print btn_a_path
        print btn_b_path
        print led_path
        print uart_path

        self.btn_a_iface = dbus.Interface(bus.get_object('org.bluez', btn_a_path), 'org.bluez.GattCharacteristic1')
        self.btn_b_iface = dbus.Interface(bus.get_object('org.bluez', btn_b_path), 'org.bluez.GattCharacteristic1')
        self.led_iface = dbus.Interface(bus.get_object('org.bluez', led_path), 'org.bluez.GattCharacteristic1')
        self.uart_iface = dbus.Interface(bus.get_object('org.bluez', uart_path), 'org.bluez.GattCharacteristic1')

        print self.btn_a_iface

    def getBtn(self):
        btn_val = self.btn_a_iface.ReadValue(dbus.Array())
        btn_a = int(btn_val[0])
        btn_val = self.btn_b_iface.ReadValue(dbus.Array())
        btn_b = int(btn_val[0])

        return (btn_a, btn_b)

    def putLed(self, msg):
        self.led_iface.WriteValue([ord(msg[0])], ())
        print "Sent", msg

    def printStatus(self):
        btn_val = self.btn_a_iface.ReadValue(dbus.Array())
        btn_a = int(btn_val[0])
        btn_val = self.btn_b_iface.ReadValue(dbus.Array())
        btn_b = int(btn_val[0])
        if btn_a > 0 and btn_b < 1:
            self.led_iface.WriteValue([ord('A')], ())
            print('Button A')        
        elif btn_a < 1 and btn_b > 0:
            print('Button B')
            self.led_iface.WriteValue([ord('B')], ())
        elif btn_a > 0 and btn_b > 0:
            message = 'Quit.'
            val = []
            for c in message:
                val.append(ord(c))
            self.uart_iface.WriteValue(val, ())
            sense_buttons = False
            print('Bye bye!!!')
        if not self.remote_device_props.Get('org.bluez.Device1', 'Connected'):  
            sense_buttons = False

    def __del__(self):
        self.remote_device_methods.Disconnect()
 
if __name__ == '__main__':
    name = sys.argv[1]
    global bt
    bt = Bluetooth(name)
    ws_app = Application()
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(PORT)
    print "Starting"
    tornado.ioloop.IOLoop.instance().start()
