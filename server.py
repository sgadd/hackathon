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
connected_microbits=[]

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
        for mb in connected_microbits:
            (btnA, btnB) = self.bt.getBtn(mb)
            if btnA>0:
                self.write_message('Button A on '+mb)
            if btnB>0:
                self.write_message('Button B on '+mb)

    def send_echo(self, message):
        self.write_message(message)

    def on_message(self, message):
        for mb in connected_microbits:
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

        device_paths=dict()

        self.btn_a_path={}
        self.btn_a_iface={}
        self.btn_b_path={}
        self.btn_b_iface={}
        self.led_path={}
        self.led_iface={}
        self.uart_path={}
        self.uart_iface={}

        remote_device_obj={}
        self.remote_device_methods = {}
        self.remote_device_props = {}
        device_paths={}
        pending_microbits=[]
        remaining_names=list(names)
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
                                pending_microbits.append(name)

                                remote_device_obj[name] = bus.get_object('org.bluez', device_paths[name])
                                self.remote_device_methods[name] = dbus.Interface(remote_device_obj[name], 'org.bluez.Device1')
                                self.remote_device_props[name] = dbus.Interface(remote_device_obj[name], dbus.PROPERTIES_IFACE)

                                self.remote_device_methods[name].Connect()

        n=0
        while len(pending_microbits)>0 and n<100:
            sleep(0.1)
            n+=1
            if n%10==0:
                print n/10
            for mb in pending_microbits:
                if self.remote_device_props[mb].Get('org.bluez.Device1','ServicesResolved'):
                    pending_microbits.remove(mb)
                    connected_microbits.append(mb)
                    print "Connected to", mb

                    device_path = device_paths[mb]
                    for obj, ifaces in objects.items():
                        if 'org.bluez.GattCharacteristic1' in ifaces.keys():
                            if obj.startswith(device_path):
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dda90-251d-470a-a062-fa1922dfa9a8':
                                    self.btn_a_path[mb] = obj
                                    self.btn_a_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_a_path[mb]), 'org.bluez.GattCharacteristic1')
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dda91-251d-470a-a062-fa1922dfa9a8':
                                    self.btn_b_path[mb] = obj
                                    self.btn_b_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_b_path[mb]), 'org.bluez.GattCharacteristic1')
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95d93ee-251d-470a-a062-fa1922dfa9a8':
                                    self.led_path[mb] = obj
                                    self.led_iface[mb]   = dbus.Interface(bus.get_object('org.bluez', self.led_path[mb]  ), 'org.bluez.GattCharacteristic1')
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == '6e400003-b5a3-f393-e0a9-e50e24dcca9e':
                                    self.uart_path[mb] = obj
                                    self.uart_iface[mb]  = dbus.Interface(bus.get_object('org.bluez', self.uart_path[mb] ), 'org.bluez.GattCharacteristic1')

                    print "Interface setup for", mb

        print "Number of connected devices:", len(connected_microbits)

    def getBtn(self, name):
        btn_val = self.btn_a_iface[name].ReadValue(dbus.Array())
        btn_a = int(btn_val[0])
        btn_val = self.btn_b_iface[name].ReadValue(dbus.Array())
        btn_b = int(btn_val[0])

        return (btn_a, btn_b)

    def putLed(self, name, msg):
        self.led_iface[name].WriteValue(map(ord, msg), ())
        print "Sent", msg

    def __del__(self):
        for mb in connected_microbits:
            self.remote_device_methods[mb].Disconnect()

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

