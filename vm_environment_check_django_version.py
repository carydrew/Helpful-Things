#!/usr/bin/env python
#
# Cary Drew - August 2021 - Proof of Concept (little to no error checks)
#  - Does what I needed for work and I moved on (search for a user's folder in a folder that has about 150 users with similar VM names and query those VMs)
#  - took the base from cpaggen's getvnicinfo.py and adjusted it to work in my Django app, this version works via django. 
#     - There is a cmd line version in my github.
#     - Made cpaggen's faster as it ignores a lot of the uneeded hosts/ESXi/VMs that I don't care about
#  - I made a few comments to help my error checking.
#
# Error checking done via Django functions 
#
# Calling the env_check() function via django starts it all
#
# Known Errors: 
# - If a VM is powering up/down when checked it will cause an issue.

from __future__ import print_function

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from . import views # This import is for the error checking of the fucntion No_userFolder
import atexit
import sys

# Start Error check? - I don't this actually works. But the version in my views.py does.
def No_userFolder(request):
    views.enviro_error(request)

# End of the error check. This is a very crappy way to do it. 

def GetVMHosts(content):
    
    host_view = content.viewManager.CreateContainerView(content.rootFolder,
                                                        [vim.HostSystem],
                                                        True)
    obj = [host for host in host_view.view if "esxi" in host.name]
    host_view.Destroy()
    return obj

def GetHostsPortgroups(hosts):
    
    hostPgDict = {}
    for host in hosts:
        pgs = host.config.network.portgroup
        hostPgDict[host] = pgs

    return hostPgDict


def PrintVmInfo(vm, ipAddy):
    connectionState = vm.runtime.connectionState
    vmPowerState = vm.runtime.powerState
    conn_power = vmPowerState + " - " + connectionState
    listIP, portGroup, vlanId = GetVMNics(vm, ipAddy)
    return conn_power, listIP, portGroup, vlanId


def GetVMNics(vm, ipAddy):
    i = 0
    for dev in vm.config.hardware.device:
        if isinstance(dev, vim.vm.device.VirtualEthernetCard):
            dev_backing = dev.backing
            portGroup = None
            vlanId = None
            vSwitch = None
            if hasattr(dev_backing, 'port'):
                portGroupKey = dev.backing.port.portgroupKey
                dvsUuid = dev.backing.port.switchUuid
                try:
                    dvs = content.dvSwitchManager.QueryDvsByUuid(dvsUuid)
                    # This except causes a lot of issues, I pulled this with the basic function pre-edit so it's just commented out for now.
                    # It may get deleted later. 
                #except:
                #    portGroup = "** Error: DVS not found **"
                #    vlanId = "NA"
                #    vSwitch = "NA"
                finally:
                    pgObj = dvs.LookupDvPortGroup(portGroupKey)
                    portGroup = pgObj.config.name
                    vlanId = str(pgObj.config.defaultPortConfig.vlan.vlanId)
                    vSwitch = str(dvs.name)
            else:
                portGroup = dev.backing.network.name
                vmHost = vm.runtime.host
                # global variable hosts is a list, not a dict
                host_pos = hosts.index(vmHost)
                viewHost = hosts[host_pos]
                # global variable hostPgDict stores portgroups per host
                pgs = hostPgDict[viewHost]
                for p in pgs:
                    if portGroup in p.key:
                        vlanId = str(p.spec.vlanId)
                        vSwitch = str(p.spec.vswitchName)
            if portGroup is None:
                portGroup = 'NA'
            if vlanId is None:
                vlanId = 'NA'
            if vSwitch is None:
                vSwitch = 'NA'

            # Checking for machines that don't have vmware tools - can't pull the IP on those vms.
            if vm.guest.toolsRunningStatus != "guestToolsRunning" and vm.runtime.powerState == "poweredOn":
                thisIP = "VMware Tools is not installed on this VM."

            # This will cut out IPv6 IPs. Put all IPv4 IPs in a list, then make it a string. 
            elif vm.runtime.powerState == "poweredOn" :
                while i < len(ipAddy):
                    splitIP = str(ipAddy[i].ipAddress)
                    splitIP = splitIP[11:-1].split("'")
                    listIP = []
                    for ip in splitIP:
                        if '.' in ip:
                            listIP.append(ip)
                    thisIP = ", ".join(listIP)
                    i += 1
            
            # Checking for machines that are powered off - otherwise it throws an error for the IP
            elif vm.runtime.powerState != "poweredOn" :
                thisIP = ""

    return thisIP, portGroup, vlanId
            

def GetArgs(request):
    if len(sys.argv) != 4:
        host = "vcenter.domain.com"
        Query_user = request.POST.get('Query_username')
        password = request.POST.get('password')
    else:
        host, Query_user, password = sys.argv[1:]
    return host, Query_user, password

def User_Folder(request):
    global hosts, hostPgDict, content

    user_name = request.POST.get('user')
    host, Query_user, password = GetArgs(request)
    serviceInstance = SmartConnect(host=host,
                                   user=Query_user,
                                   pwd=password,
                                   port=443)
    atexit.register(Disconnect, serviceInstance)
    content = serviceInstance.RetrieveContent()
    hosts = GetVMHosts(content)
    hostPgDict = GetHostsPortgroups(hosts)
        # Getting the User specific folder and VMs
    obj = content.searchIndex.FindByInventoryPath("dc/vm/foo/bar")        
        # This will pull the specific requested users stuff
    for vm_folders in obj.childEntity:
        if vm_folders.name == user_name:
            userFolder = vm_folders
            return userFolder
    


def env_check(request): # This is the main function

    # The answer list/dict is the what actually holds each item to return to the django template
    answer = []

    User_folder = User_Folder(request)
    if hasattr(User_folder, 'childEntity'):

        for vms in User_folder.childEntity:
            for UserItem in vms.childEntity:
                if hasattr(UserItem ,'childEntity'):
                    for vm in UserItem.childEntity:
                        ipAddy = vm.guest.net
                        conn_power, listIP, portGroup, vlanId = PrintVmInfo(vm, ipAddy)
                        answer.append({
                                        "name" : UserItem.name[7:] + " - " + vm.name,
                                        "power" : conn_power,
                                        "port": portGroup,
                                        "ip" : listIP,
                                        "vlan" : vlanId})
                else: 
                    ipAddy = UserItem.guest.net
                    conn_power, listIP, portGroup, vlanId = PrintVmInfo(UserItem, ipAddy)
                    answer.append({
                                    "name" : UserItem.name,
                                    "power" : conn_power,
                                    "port": portGroup,
                                    "ip" : listIP,
                                    "vlan" : vlanId})
                
        return answer


def vm_user_query(request):
    host, Query_user, password = GetArgs(request)
    serviceInstance = SmartConnect(host=host,
                                   user=Query_user,
                                   pwd=password,
                                   port=443)
    atexit.register(Disconnect, serviceInstance)
    content = serviceInstance.RetrieveContent()
        # Getting the User specific folder and VMs
    obj = content.searchIndex.FindByInventoryPath("dc/vm/foo/bar")
        # trying to list vms in a user folder 
            # This will pull all the users listed in vCenter
    vm_users = []
    for vm_folders in obj.childEntity:
        the_name = vm_folders.name
        vm_users.append(the_name[:-15])
    vm_users.sort()
    return vm_users