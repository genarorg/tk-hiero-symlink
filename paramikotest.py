__author__ = 'genarorg'
import sys
import os
import platform
import select
import paramiko

def executeCommand(command, ssh):

        stdin, stdout, stderr = ssh.exec_command(command)
        while not stdout.channel.exit_status_ready():
            if stdout.channel.recv_ready():
                for line in stdout.read().splitlines():
                    print line
            if stderr.channel.recv_stderr_ready():
                for line in stderr.read().splitlines():
                    print line

def connectParamiko(addr, user, _password):

        #Init Paramiko
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy( paramiko.AutoAddPolicy() )
            ssh.connect(addr, username=user, password=_password)
            return ssh
        except paramiko.AuthenticationException:
            print "Authentication failed when connecting to %s" % addr
        except:
            print "Could not connect to host"

ssh = connectParamiko("192.168.1.34", "boxel", "boxel")
for i   in range(0,5):
    executeCommand("ls -l; sleep 5", ssh)
print "exiting"

