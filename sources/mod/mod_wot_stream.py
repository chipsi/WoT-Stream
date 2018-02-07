import re
import atexit
import subprocess
import _winreg as winreg
from warnings import warn
from socket import socket

from gui import InputHandler
from gui.Scaleform import SCALEFORM_SWF_PATH
from gui.Scaleform.Flash import Flash
from gui.Scaleform.daapi import LobbySubView
from gui.Scaleform.daapi.view.meta.WindowViewMeta import WindowViewMeta
from gui.Scaleform.framework import g_entitiesFactories, ViewSettings, ViewTypes, ScopeTemplates
from gui.Scaleform.framework.entities.View import View
from gui.Scaleform.framework.managers.loaders import ViewLoadParams
from gui.app_loader.loader import g_appLoader
from gui.shared import events
from gui.shared.utils.key_mapping import getBigworldNameFromKey

LobbySubView.__background_alpha__ = 0

class Protocol(object): # I Want Enums

    def __init__(self):

        # ordinary responses
        self.__ok = 'ok'
        self.__bp = 'bp'
        self.__er = 'er'
        self.__uw = 'uw'

        # 'stat' responses
        self.__ntin = 'ntin'
        self.__stpd = 'stpd'
        self.__busy = 'busy'
        self.__srtd = 'srtd'

    # ordinary responses

    @property
    def ok(self):
        return self.__ok

    @property
    def badOperation(self):
        return self.__bp

    @property
    def error(self):
        return self.__er

    @property
    def unawailable(self):
        return self.__uw

    # 'stat' responses

    @property
    def notInitialized(self):
        return self.__ntin

    @property
    def started(self):
        return self.__srtd

    @property
    def busy(self):
        return self.__busy

    @property
    def stopped(self):
        return self.__stpd
    

class WoTStreamRemote(object):

    def __init__(self, address, port):
        self.__proto = Protocol()
        self.__address = address
        self.__port = port
        self.__sc = None
        self.__wsr = None
        self.__startWoTStream()
        self.__initializeWotStream()

    @property
    def proto(self):
        return self.__proto

    def connect(self):
        try:            
            self.__sc = socket()
            self.__sc.connect((self.__address, self.__port))
            return self.__proto.ok
        except:
            return self.__proto.unawailable

    def getState(self):
        return self.__safeRemoteExec('stat', 4)

    def initialize(self):
        return self.__safeRemoteExec('init')

    def updateToken(self, token):
        return self.__safeRemoteExec('updt: ' + token)

    def startStream(self):
        return self.__safeRemoteExec('srts')

    def stopStream(self):
        return self.__safeRemoteExec('stps')    

    def __safeRemoteExec(self, command, response_length=2):
        try:
            return self.__send(command, response_length)
        except:
            return self.__proto.unawailable

    def __send(self, command, response_length):
        self.__sc.send(command)
        return self.__sc.recv(response_length)
    
    def __startWoTStream(self):
        wsr_path = self.__getRegValue(r'Software\WoT Stream', 'InstallPath')
        full_name = wsr_path + r'\wot_stream.exe'
        sinfo = subprocess.STARTUPINFO()
        sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        wsr = subprocess.Popen(full_name, cwd=wsr_path, startupinfo=sinfo)
        atexit.register(wsr.kill)

    def __initializeWotStream(self):
        self.connect()
        self.initialize()

    def __getRegValue(self, path, name):
        try:
            registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
            value, regtype = winreg.QueryValueEx(registry_key, name)
            winreg.CloseKey(registry_key)
            return value
        except WindowsError:
            return None


class WotStreamViewState(object):

    def __init__(self):
        self.WSR = WoTStreamRemote('127.0.0.1', 48684)
        self.pattern = re.compile(r'^[a-z0-9]{4,4}-[a-z0-9]{4,4}-[a-z0-9]{4,4}-[a-z0-9]{4,4}', re.IGNORECASE)

        self.help = "Enter your token below and click 'Start Stream'!"
        self.inputEnabled = True
        self.token = ''
        self.btnEnabled = False
        self.btnLabel = 'Start Stream'
        self.statusText = 'unknown'


g_ws_ViewState = WotStreamViewState()

class WoTStreamView(LobbySubView, WindowViewMeta):

    def __init__(self):
        View.__init__(self)
        global g_ws_ViewState
        self.__state = g_ws_ViewState
        self.WSR = self.__state.WSR
        self.proto = self.WSR.proto
        print 'WSR: View --- init ok'

    def onFocusIn(self, alias):
        self.__loadState()

    def onTryClosing(self):
        return True

    def onWindowClose(self):
        self.destroy()

    def _dispose(self):
        View._dispose(self)

    def __loadState(self):
        self.__setHelpText(self.__state.help)
        self.__setInputEnabled(self.__state.inputEnabled)
        self.__setInputText(self.__state.token)
        self.__setBtnEnabled(self.__state.btnEnabled)
        self.__setBtnLabel(self.__state.btnLabel)
        self.__setStatusText(self.__state.statusText)
        print 'WSR: View --- state loaded'

    # -- from view
    def checkInput(self, input):

        input_valid = False

        if input and len(input) == 19:
            match = self.__state.pattern.match(input)
            if match:
                self.__state.token = match.group(0)
                input_valid = True

        self.__onInputValidate(input_valid)

    # -- from view
    def startStopStream(self, token):        

        state = self.WSR.getState()

        if state == self.proto.unawailable:
            self.__onConnect(self.WSR.connect())            

        elif state == self.proto.notInitialized:
            self.__onInitialize(self.WSR.initialize())            

        elif state == self.proto.stopped:
            self.WSR.updateToken(self.__state.token)
            self.__onStreamStart(self.WSR.startStream())            

        elif state == self.proto.busy:
            self.__onBusy()

        elif state == self.proto.started:
            self.__onStreamStop(self.WSR.stopStream())            
        else:
            pass

    def __onConnect(self, result):
        if result == self.proto.ok:
            self.__setHelpText("Connected, click 'Initialize'")
            self.__setInputEnabled(False)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Initialize')
            self.__setStatusText('connection successfully')
            print 'WSR: connection successfully'
        else:
            self.__setHelpText("Run the companion app and click 'Connect'")
            self.__setInputEnabled(False)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Try Again')
            self.__setStatusText("connection failed, wot_stream.exe isn't available")
            print "WSR: connection failed, wot_stream.exe isn't available"

    def __onInitialize(self, result):
        if result == self.proto.ok:
            self.__setHelpText("Enter your token below and click 'Start Stream'!")
            self.__setInputEnabled(True)
            self.__setBtnEnabled(False)
            self.__setBtnLabel('Start Stream')
            self.__setStatusText('initialization completed successfully')
            print 'WSR: initialization completed successfully'
        else:
            self.__setHelpText("Run the companion app and click 'Connect'")
            self.__setInputEnabled(False)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Try Again')
            self.__setStatusText('initialization failed, something went wrong')
            print 'WSR: initialization failed, something went wrong'

    def __onStreamStart(self, result):
        if result == self.proto.ok:
            self.__setHelpText("Stream started! You can close this window")
            self.__setInputEnabled(False)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Stop Stream')
            self.__setStatusText('stream started')
            print 'WSR: stream started'
        elif result == self.proto.error: #invalid token
            self.__setHelpText("Could not start the stream")
            self.__setInputEnabled(True)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Try Again')
            self.__setStatusText("Invalid stream token or rtmp-server isn't available")
            print 'WSR: start stream fail, bad token'
        else:
            self.__setHelpText("Could not start the stream")
            self.__setInputEnabled(True)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Try Again')
            self.__setStatusText('wot stream not ready')
            print 'WSR: start stream fail, wot stream not ready'

    def __onBusy(self):
        self.__setHelpText("Operation failed")
        self.__setInputEnabled(True)
        self.__setBtnEnabled(True)
        self.__setBtnLabel('Try Again')
        self.__setStatusText('wot stream not ready')
        print 'WSR: busy, operation failed, wot stream not ready'

    def __onStreamStop(self, result):
        if result == self.proto.ok:
            self.__setHelpText("Stream stopped!")
            self.__setInputEnabled(True)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Start Stream')
            self.__setStatusText('stream stopped')
            print 'WSR: stream started'
        else:
            self.__setHelpText("Could not stop the stream")
            self.__setInputEnabled(True)
            self.__setBtnEnabled(True)
            self.__setBtnLabel('Try Again')
            self.__setStatusText('wot stream not ready')
            print 'WSR: stop stream fail, wot stream not ready'


    def __onInputValidate(self, valid):
        if valid:
            self.__setStatusText('token valid')
            self.__setBtnLabel('Start Stream')
        else:
            self.__setStatusText('invalid token')
        self.__setBtnEnabled(valid)
    

    # -- to view
    def __setHelpText(self, text):
        self.__state.help = text
        self.flashObject.SetHelpTextFieldText(text)

    # -- to view
    def __setInputEnabled(self, enabled):
        self.__state.inputEnabled = enabled
        self.flashObject.SetTokenInputEnabled(enabled)

    # -- to view
    def __setInputText(self, text):
        self.__state.token = text
        self.flashObject.SetTokenInputText(text)

    # -- to view
    def __setBtnEnabled(self, enabled):
        self.__state.btnEnabled = enabled
        self.flashObject.SetStartStopButtonEnabled(enabled)

    # -- to view
    def __setBtnLabel(self, label):
        self.__state.btnLabel = label
        self.flashObject.SetStartStopButtonLabel(label)

    # -- to view
    def __setStatusText(self, text):
        self.__state.statusText = text
        self.flashObject.SetStatusTextFieldText(text)


_window_alias = 'WotStreamView'
_url = 'wot_stream.swf'
_type = ViewTypes.WINDOW
_event = None
_scope = ScopeTemplates.GLOBAL_SCOPE

_settings = ViewSettings(_window_alias, WoTStreamView, _url, _type, _event, _scope)
g_entitiesFactories.addSettings(_settings)

old_init = Flash.__init__


def on_key_event(event):
    key = getBigworldNameFromKey(event.key)
    if key == 'KEY_F10':
        g_appLoader.getApp().loadView(ViewLoadParams(_window_alias, _window_alias))


def new_init(self, swf, className='Flash', args=None, path=SCALEFORM_SWF_PATH):
    old_init(self, swf, className, args, path)
    if swf == 'lobby.swf':
        self.addListener(events.AppLifeCycleEvent.INITIALIZED, lambda e: subscribe(self, e))


def subscribe(self, event):
    InputHandler.g_instance.onKeyDown += on_key_event


Flash.__init__ = new_init