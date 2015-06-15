from PySide import QtGui
from PySide import QtCore

import hiero.core

from tank.platform import Application
from tank import TankError
import sgtk
import sys
import os
import platform
import time
import select

# do not use tk import here, hiero needs the classes to be in their
# standard namespace, hack to get the right path in sys.path
pythonpath = os.path.join(os.path.dirname(__file__), "python")
vendorpath = os.path.join(pythonpath, "vendor")
sys.path.append(pythonpath)
sys.path.append(vendorpath)
import paramiko


class HieroCreateSymlinks(Application):
    """
    SGTK application for hiero that creates symlinks from selected track items into their
    respective shots according to the current pipeline configuration
    """

    def init_app(self):
        """
        Initialization
        """
        self.engine.register_command("Create Symlinks", self.callback)

    def callback(self):
        """
        Command implementation
        """
        try:
            self._create_symlinks()
        except TankError, e:
            # report all tank errors with a UI popup.
            QtGui.QMessageBox.critical(None, "Shot Lookup Error!", str(e))
        except Exception, e:
            # log full call stack to console
            self.log_exception("General error reported.")
            # pop up message
            msg = "A general error was reported: %s" % e
            QtGui.QMessageBox.critical(None, "Shot Lookup Error!", msg)
        finally:
            QtGui.QMessageBox.critical(None, "Finished", "All done!")

    def _create_symlinks(self):

        """
        Grab the source frames from selection
        Grab the shot name and find it in shotgun
        Load the shot context to find the appropriate destination path
        Connect to file server (linux) and create the symlinks.
        """

        # grab the current selection from the view that triggered the event
        selection = self.engine.get_menu_selection()

        if len(selection) != 1:
            raise TankError("Please select a single Shot!")

        if not isinstance(selection[0] , hiero.core.TrackItem):
            raise TankError("Please select a Shot in the Timeline or Spreadsheet!")

        trackItem = selection[0]
        shot_name = trackItem.name()
        splitName = shot_name.split("_")
        episodeCode = splitName[0]+"_"+splitName[1]
        sequenceCode = episodeCode +"_"+ splitName[2]

        filters = [
            ['project', 'is', self.engine.context.project],
            ['sg_sequence.Sequence.code','is', sequenceCode],
            ['sg_sequence.Sequence.sg_episode.CustomEntity01.code', 'is', episodeCode],
            ['code', 'is', shot_name],
        ]
        sg_data = self.shotgun.find_one("Shot", filters)
        if sg_data is None:
            raise TankError("Could not find a Shot in Shotgun with name '%s' associated with a Sequence '%s' in Episode!" % (shot_name, sequenceCode, episodeCode))

        #get all the configuration variables
        serverAddress = self.get_setting("server_address")
        serverUserName = self.get_setting("server_user")
        serverPassword = self.get_setting("server_password")
        template_obj = self.get_template("template_symlinks")

        #get the template from the provided template, as defined in the environment configuration (project.yml)
        fields = self.context.as_template_fields(template_obj)
        fields['CustomEntity01'] = episodeCode
        fields['Sequence'] = sequenceCode
        fields['Shot'] = shot_name

        #This is the location on which the symlinks will be generated, this is the toolkit root
        symlinksPath = template_obj.apply_fields(fields)

        #Init Paramiko
        ssh = self.connectParamiko(serverAddress, serverUserName, serverPassword)

        #grab the clip frames and create the symlink command for each
        if trackItem.isMediaPresent():
            mediaSource = trackItem.source().mediaSource()
            commands = self.createSymlinks(mediaSource, symlinksPath, ssh, shot_name)
            ssh.close()

        else:
            raise TankError("There is no media associated with this shot")


    def getPathInServer(self, path):

        serverRoot = self.get_setting("server_root")
        if platform.system() == 'Windows':
            # If this is a windows workstation, the toolkit path will come as a windows path,
            # we need to convert the path to unix type so we can pass it along to the server
            pass

        if platform.system() =='Linux':
            #remove the first forward slash
            if path[0] == "/" :
                path = path[1:]

        return os.path.join(serverRoot, path)

    def createSymlinks(self, mediaSource, symlinksPath, ssh, shot_name):

        symlinksList = []
        files = mediaSource.fileinfos()
        if not os.path.exists(symlinksPath):
            self.executeCommand("mkdir %s" % (self.getPathInServer(symlinksPath)), ssh)
        if mediaSource.singleFile() is False:
            #if this is not a video (i.e. MOV file)
            for file in files:

                startFrame = file.startFrame()
                endFrame = file.endFrame()
                fileName = file.filename()
                fileExtension = os.path.splitext(fileName)[1]
                paddingString = "%0"+str(mediaSource.filenamePadding())+"d"

                for i in range(startFrame, endFrame + 1):

                    frame = fileName % i
                    linkFrame = (shot_name + "." + paddingString + fileExtension) % i
                    link = os.path.join(symlinksPath, linkFrame)
                    self.executeCommand(self.getSymlinkCommand(frame, link), ssh)
        else:
            #if this is a video
            self.executeCommand(self.getSymlinkCommand(files[0].filename(), symlinksPath), ssh)

        return symlinksList

    def getSymlinkCommand(self, target, link):

        linkTarget = self.getPathInServer(target)
        linkDir = self.getPathInServer(link)
        symlinkCommand = "ln -f -s {0} {1}".format(linkTarget, linkDir)
        return symlinkCommand

    def executeCommand(self, command, ssh):

        stdin, stdout, stderr = ssh.exec_command(command)
        while not stdout.channel.exit_status_ready():
            if stdout.channel.recv_ready():
                for line in stdout.read().splitlines():
                    print "out: " + line
            if stderr.channel.recv_stderr_ready():
                for line in stderr.read().splitlines():
                    print "error: " + line
                    raise TankError("Error from server: %s", line)


    def connectParamiko(self, addr, user, _password):

        #Init Paramiko
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy( paramiko.AutoAddPolicy() )
            ssh.connect(addr, username=user, password=_password)
            return ssh
        except paramiko.AuthenticationException:
            raise TankError("Authentication failed when connecting to %s" % addr)
        except:
            raise TankError("Could not connect to host")
