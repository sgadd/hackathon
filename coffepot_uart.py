import dbus
import sys, re, threading
from time import sleep
import tornado.httpserver
import tornado.websocket
import tornado.ioloop
from tornado.ioloop import PeriodicCallback
import tornado.web
from gi.repository import GObject
from dbus.mainloop.glib import DBusGMainLoop

PORT=8888

my_microbits=['gazop']
connected_microbits=[]

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        global th
        th = self
        global bt
        self.bt = bt
        print "Opened websocket"

    def on_btn_a(self, name, state):
        #print "WSH Button A", name, state
        self.write_message('0 '+name+' '+str(state))

    def on_btn_b(self, name, state):
        #print "WSH Button B", name, state
        self.write_message('1 '+name+' '+str(state))

    def on_acc(self, name, acc_x, acc_y, acc_z):
        #print "WSH acc", name, acc_x, acc_y, acc_z
        self.write_message('2 '+name+' '+str(acc_x)+' '+str(acc_y)+' '+str(acc_z))

    def on_uart(self, name, value):
        #print "WSH crt", name, value
        self.write_message('3 '+name+' '+str(value))

    def send_echo(self, message):
        self.write_message(message)

    def on_message(self, message):
        for mb in connected_microbits:
            self.bt.putLed(mb, message)

    def on_close(self):
        print "Closed websocket"


class IndexPageHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("coffe.html")
        print "Sent coffe.html"


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', IndexPageHandler),
            (r'/websocket', WebSocketHandler),
            (r'/images/(.*)',tornado.web.StaticFileHandler, {'path': "./images"})
        ]
 
        settings = {
            'template_path': ''
        }
        tornado.web.Application.__init__(self, handlers, **settings)
 

class Bluetooth():
    def __init__(self, names=['bogus']):
        self.setup(names)

    def setup(self, names):
        def btn_a_changed(name, characteristic, changed_state, dummy):
            if 'Value' in changed_state:
                btn_a_state = int(changed_state['Value'][0])
                #print name, 'button A state', str(btn_a_state)
                global th
                if th:
                    th.on_btn_a(name, btn_a_state)

        def btn_b_changed(name, characteristic, changed_state, dummy):
            if 'Value' in changed_state:
                btn_b_state = int(changed_state['Value'][0])
                #print name, 'button B state', str(btn_b_state)
                global th
                if th:
                    th.on_btn_b(name, btn_b_state)

        def acc_changed(name, characteristic, changed_state, dummy):
            if 'Value' in changed_state:
                acc_val = changed_state['Value']
                acc_x = int(acc_val[0]) + int(acc_val[1])*256;
                acc_y = int(acc_val[2]) + int(acc_val[3])*256;
                acc_z = int(acc_val[4]) + int(acc_val[5])*256;
                if acc_x >= 1<<15:
                    acc_x = acc_x - (1<<16)
                if acc_y >= 1<<15:
                    acc_y = acc_y - (1<<16)
                if acc_z >= 1<<15:
                    acc_z = acc_z - (1<<16)
                #print name, 'accelerometer value', str(acc_x), str(acc_y), str(acc_z)
                global th
                if th:
                    th.on_acc(name, acc_x, acc_y, acc_z)
        def uart_changed(charachteristic, changed_state, dummy):
                if 'Value' in changed_state:
                     value = int(changed_state['Value'][0]) - ord('0')
                     if value == 1:
                         print 'button A'
                     if value == 2:
                         print 'button B'
                     if value == 3:
                         print 'Bye bye!!!'
                         loop.quit()
                     print changed_state['Value']  
                     print "%s"%(changed_state['Value']) 
                     print "Value: "
                     print value

                global th
                if th:
                    th.on_uart(name, value)

			


        bus = dbus.SystemBus()
        bluez = bus.get_object('org.bluez','/')
        bluez_iface = dbus.Interface(bluez, 'org.freedesktop.DBus.ObjectManager')
        objects = bluez_iface.GetManagedObjects()

        device_paths=dict()

        self.btn_a_path={}
        self.btn_a_obj={}
        self.btn_a_iface={}
        self.btn_a_prop={}
        self.btn_b_path={}
        self.btn_b_obj={}
        self.btn_b_iface={}
        self.btn_b_prop={}
        self.acc_path={}
        self.acc_obj={}
        self.acc_iface={}
        self.acc_prop={}
        self.led_path={}
        self.led_iface={}
        self.uart_path={}
        self.uart_iface={}
        self.uart_obj={}
        self.uart_prop={}

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

                                print "Connecting to", name
                                self.remote_device_methods[name].Connect()

        print "Waiting for", len(pending_microbits), "microbits"
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
                                    self.btn_a_obj[mb] = bus.get_object('org.bluez', self.btn_a_path[mb])
                                    self.btn_a_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_a_path[mb]), 'org.bluez.GattCharacteristic1')
                                    self.btn_a_prop[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_a_path[mb]), dbus.PROPERTIES_IFACE)
                                    self.btn_a_prop[mb].connect_to_signal('PropertiesChanged', lambda a, b, c: btn_a_changed(mb, a, b, c))
                                    self.btn_a_obj[mb].StartNotify(dbus_interface='org.bluez.GattCharacteristic1')
                                    print 'Setup button A for', mb
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dda91-251d-470a-a062-fa1922dfa9a8':
                                    self.btn_b_path[mb] = obj
                                    self.btn_b_obj[mb] = bus.get_object('org.bluez', self.btn_b_path[mb])
                                    self.btn_b_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_b_path[mb]), 'org.bluez.GattCharacteristic1')
                                    self.btn_b_prop[mb] = dbus.Interface(bus.get_object('org.bluez', self.btn_b_path[mb]), dbus.PROPERTIES_IFACE)
                                    self.btn_b_prop[mb].connect_to_signal('PropertiesChanged', lambda a, b, c: btn_b_changed(mb, a, b, c))
                                    self.btn_b_obj[mb].StartNotify(dbus_interface='org.bluez.GattCharacteristic1')
                                    print 'Setup button B for', mb
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95d93ee-251d-470a-a062-fa1922dfa9a8':
                                    self.led_path[mb] = obj
                                    self.led_iface[mb]   = dbus.Interface(bus.get_object('org.bluez', self.led_path[mb]  ), 'org.bluez.GattCharacteristic1')
                                    print 'Setup LED for', mb
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == 'e95dca4b-251d-470a-a062-fa1922dfa9a8':
                                    self.acc_path[mb] = obj
                                    self.acc_obj[mb] = bus.get_object('org.bluez', self.acc_path[mb])
                                    self.acc_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.acc_path[mb]), 'org.bluez.GattCharacteristic1')
                                    self.acc_prop[mb] = dbus.Interface(bus.get_object('org.bluez', self.acc_path[mb]), dbus.PROPERTIES_IFACE)
                                    self.acc_prop[mb].connect_to_signal('PropertiesChanged', lambda a, b, c: acc_changed(mb, a, b, c))
                                    self.acc_obj[mb].StartNotify(dbus_interface='org.bluez.GattCharacteristic1')
                                    print 'Setup accelerometer for', mb
                                
                                # UUID for reading uartdata sent from microbit
                                if ifaces['org.bluez.GattCharacteristic1']['UUID'] == '6e400002-b5a3-f393-e0a9-e50e24dcca9e':
                                    self.uart_path[mb] = obj
                                    self.uart_obj[mb] = bus.get_object('org.bluez', self.uart_path[mb])
                                    self.uart_iface[mb] = dbus.Interface(bus.get_object('org.bluez', self.uart_path[mb]), 'org.bluez.GattCharacteristic1')
                                    self.uart_prop[mb] = dbus.Interface(bus.get_object('org.bluez', self.uart_path[mb]), dbus.PROPERTIES_IFACE)
                                    self.uart_prop[mb].connect_to_signal('PropertiesChanged', lambda a, b, c: uart_changed(a, b, c))
                                    self.uart_obj[mb].StartNotify(dbus_interface='org.bluez.GattCharacteristic1')
                                    print 'Setup uart for', mb
                                    print "uart connected"
                                    pass

        print "Number of connected microbits:", len(connected_microbits)

        GObject.threads_init()
        myT = threading.Thread(target=GObject.MainLoop().run)
        myT.start()
        print "Started bt"

    def putLed(self, name, msg):
        val=[]
        for c in msg:
            val.append(ord(c))
        self.led_iface[name].WriteValue(val, ())
        #print "Sent", msg, "to", name

    def __del__(self):
        for mb in connected_microbits:
            self.remote_device_methods[mb].Disconnect()


def main():
    DBusGMainLoop(set_as_default=True)

    global th
    th = None

    global bt
    bt = Bluetooth(my_microbits)

    ws_app = Application()
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(PORT)
    print "Starting tornado"
    tornado.ioloop.IOLoop.instance().start()


if __name__=='__main__':
   main()

