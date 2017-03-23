import dbus
import sys, re
from time import sleep
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
from tornado.ioloop import PeriodicCallback
import tornado.web

PORT=8888

my_microbits=['zotev', 'vevez']

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global bt
        self.bt = bt
        self.callback = PeriodicCallback(self.check_status, 10)
        self.callback.start()
        print "Opened Connection"

    def check_status(self):
        for mb in my_microbits:
            (btnA, btnB) = self.bt.getBtn(mb)
            if btnA>0:
                self.write_message('Button A on '+mb)
            if btnB>0:
                self.write_message('Button B on '+mb)

    def send_echo(self, message):
        self.write_message(message)

    def on_message(self, message):
        for mb in my_microbits:
            self.bt.putLed(mb, message)
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
    def __init__(self, names=['bogus']):
        self.setup(names)

    def setup(self, names):
        bus = dbus.SystemBus()
        bluez = bus.get_object('org.bluez','/')
        bluez_iface = dbus.Interface(bluez, 'org.freedesktop.DBus.ObjectManager')
        objects = bluez_iface.GetManagedObjects()

        remaining_names=list(names)
        device_paths=dict()

        while len(remaining_names)>0:
            for obj, ifaces in objects.items():
                if 'org.bluez.Device1' in ifaces.keys():
                    if 'Name' in ifaces['org.bluez.Device1']:
                        m=re.search('BBC micro:bit \[(\w+)\]', ifaces['org.bluez.Device1']['Name'])
                        if m:
                            name=m.group(1)
                            if name in remaining_names:
                                print "Matched", name
                                device_paths[name] = obj
                                remaining_names.remove(name)

        print device_paths

        self.btn_a_iface={}
        self.btn_b_iface={}
        self.led_iface={}
        self.uart_iface={}

        for name, device_path in device_paths.iteritems():
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

            self.btn_a_iface[name] = dbus.Interface(bus.get_object('org.bluez', btn_a_path), 'org.bluez.GattCharacteristic1')
            self.btn_b_iface[name] = dbus.Interface(bus.get_object('org.bluez', btn_b_path), 'org.bluez.GattCharacteristic1')
            self.led_iface[name] = dbus.Interface(bus.get_object('org.bluez', led_path), 'org.bluez.GattCharacteristic1')
            self.uart_iface[name] = dbus.Interface(bus.get_object('org.bluez', uart_path), 'org.bluez.GattCharacteristic1')

        print self.btn_a_iface

    def getBtn(self, name):
        btn_val = self.btn_a_iface[name].ReadValue(dbus.Array())
        btn_a = int(btn_val[0])
        btn_val = self.btn_b_iface[name].ReadValue(dbus.Array())
        btn_b = int(btn_val[0])

        return (btn_a, btn_b)

    def putLed(self, name, msg):
        self.led_iface[name].WriteValue([ord(msg[0])], ())
        print "Sent", msg

    def printStatus(self, name):
        btn_val = self.btn_a_iface[name].ReadValue(dbus.Array())
        btn_a = int(btn_val[0])
        btn_val = self.btn_b_iface[name].ReadValue(dbus.Array())
        btn_b = int(btn_val[0])
        if btn_a > 0 and btn_b < 1:
            self.led_iface[name].WriteValue([ord('A')], ())
            print('Button A')        
        elif btn_a < 1 and btn_b > 0:
            print('Button B')
            self.led_iface[name].WriteValue([ord('B')], ())
        elif btn_a > 0 and btn_b > 0:
            message = 'Quit.'
            val = []
            for c in message:
                val.append(ord(c))
            self.uart_iface[name].WriteValue(val, ())
            sense_buttons = False
            print('Bye bye!!!')
        if not self.remote_device_props.Get('org.bluez.Device1', 'Connected'):  
            sense_buttons = False

    def __del__(self):
        self.remote_device_methods.Disconnect()

def main():
    global bt
    bt = Bluetooth(my_microbits)
    ws_app = Application()
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(PORT)
    print "Starting"
    tornado.ioloop.IOLoop.instance().start()

if __name__=='__main__':
   main()

